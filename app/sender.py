from __future__ import annotations

import random
import secrets
from urllib.parse import urlsplit

from playwright.async_api import Page

from app.douyin import DouyinChat, PageOperationError, first_visible
from app.models import Message, Sticker
from app.selectors import IMAGE_INPUTS, STICKER_BUTTONS, STICKER_PANELS


LATEST_OUTGOING_MESSAGE = (
    '.messageMessageListlist [data-index="0"] '
    '.messageMessageBoxmessageBox:has(.messageMessageBoxcontentBox.messageMessageBoxisFromMe)'
)
STICKER_CONFIRM_ANCHOR = "data-douyin-sender-anchor"
TEXT_CONFIRM_TIMEOUT_MS = 30_000
TEXT_CONFIRM_GRACE_MS = 2_000
STICKER_FAILURE_MARKERS = (
    "text=发送失败",
    '[aria-label*="重试"]',
    '[title*="重试"]',
    '[class*="sendFailed"]',
    '[class*="SendFailed"]',
)


async def send_message(page: Page, chat: DouyinChat, message: Message, stickers: dict[str, Sticker]) -> None:
    if message.type == "random":
        await send_message(page, chat, random.choice(message.choices), stickers)
        return
    if message.type == "text":
        await send_text(chat, message.content or "")
        return
    if message.type == "image":
        if message.path is None:
            raise PageOperationError("图片消息缺少文件路径")
        await send_image(page, message.path.as_posix())
        return
    if message.type == "douyin_sticker":
        sticker = stickers.get(message.sticker or "")
        if sticker is None:
            raise PageOperationError(f"没有原生表情映射: {message.sticker}")
        await send_douyin_sticker(page, sticker)
        return
    raise PageOperationError(f"不支持的消息类型: {message.type}")


async def send_text(chat: DouyinChat, content: str) -> None:
    editor = await chat.message_input()
    page = editor.page
    before = await _mark_latest_outgoing_message(page)
    await editor.click()
    await page.keyboard.insert_text(content)
    await page.keyboard.press("Enter")
    await _confirm_text_sent(page, before, content)


async def _confirm_text_sent(page: Page, before: tuple[str, str], content: str) -> None:
    anchor, before_content = before
    try:
        await page.wait_for_function(
            """([selector, anchor, previousContent, expectedText]) => {
                const message = document.querySelector(selector);
                if (!message) return false;
                const body = message.querySelector('[data-e2e="msg-item-content"]') || message;
                const isNewMessage =
                    message.getAttribute('data-douyin-sender-anchor') !== anchor ||
                    body.innerHTML !== previousContent;
                if (!isNewMessage) return false;
                const normalize = value => (value || '').normalize().replace(/\\s+/g, ' ').trim();
                return normalize(body.textContent).includes(normalize(expectedText));
            }""",
            arg=[LATEST_OUTGOING_MESSAGE, anchor, before_content, content],
            timeout=TEXT_CONFIRM_TIMEOUT_MS,
        )
    except Exception as exc:
        # The Douyin page can receive its own message just after Playwright's wait
        # expires, especially when the runner's IM WebSocket reconnects. Give the
        # DOM one final short window and inspect the newest outgoing message directly.
        await page.wait_for_timeout(TEXT_CONFIRM_GRACE_MS)
        try:
            confirmed = await _latest_outgoing_text_matches(page, anchor, before_content, content)
        except Exception:
            confirmed = False
        if not confirmed:
            raise PageOperationError("文字消息已触发发送，但无法确认是否发送成功；为避免重复不会自动重试") from exc
    finally:
        await _clear_confirmation_anchors(page)


async def _latest_outgoing_text_matches(
    page: Page,
    anchor: str,
    before_content: str,
    expected_text: str,
) -> bool:
    latest = page.locator(LATEST_OUTGOING_MESSAGE).first
    if not await latest.count():
        return False
    body = latest.locator('[data-e2e="msg-item-content"]').first
    if not await body.count():
        body = latest
    current_anchor = await latest.get_attribute(STICKER_CONFIRM_ANCHOR)
    current_content = await body.inner_html()
    if current_anchor == anchor and current_content == before_content:
        return False
    actual = " ".join((await body.inner_text()).split())
    expected = " ".join(expected_text.split())
    return expected in actual


async def send_image(page: Page, image_path: str) -> None:
    file_input = None
    for selector in IMAGE_INPUTS:
        candidate = page.locator(selector).first
        if await candidate.count():
            file_input = candidate
            break
    if file_input is None:
        raise PageOperationError("找不到图片上传控件")
    await file_input.set_input_files(image_path)
    await page.wait_for_timeout(1_500)

    send_button = page.get_by_role("button", name="发送", exact=True)
    if await send_button.count() and await send_button.first.is_visible():
        await send_button.first.click()
    else:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(1_000)


async def send_douyin_sticker(page: Page, sticker: Sticker) -> None:
    before = await _mark_latest_outgoing_message(page)
    button = await first_visible(page, STICKER_BUTTONS)
    await button.click(force=True)
    panel = await first_visible(page, STICKER_PANELS)

    if sticker.category:
        category = panel.get_by_text(sticker.category, exact=True)
        if await category.count() and await category.first.is_visible():
            await category.first.click()

    name = sticker.accessible_name or sticker.name
    item = panel.locator('.emojiEmojiItememojiItem').filter(has_text=name)
    for index in range(await item.count()):
        candidate = item.nth(index)
        description = candidate.locator('.emojiEmojiItememojiItemDesc')
        if await description.count() and (await description.first.inner_text()).strip() == name:
            await _click_and_confirm_sticker(page, candidate, before, name)
            return

    candidates = (
        panel.get_by_role("img", name=name, exact=True),
        panel.get_by_role("button", name=name, exact=True),
        panel.locator(f'[aria-label="{_css_escape(name)}"]'),
        panel.locator(f'[title="{_css_escape(name)}"]'),
        panel.locator(f'[alt="{_css_escape(name)}"]'),
    )
    for candidate in candidates:
        if await candidate.count() and await candidate.first.is_visible():
            await _click_and_confirm_sticker(page, candidate.first, before, name)
            return

    if sticker.fallback_index is not None:
        items = panel.locator('[role="button"], img, [aria-label], [title]')
        if await items.count() > sticker.fallback_index:
            await _click_and_confirm_sticker(page, items.nth(sticker.fallback_index), before, name)
            return
    raise PageOperationError(f"在抖音表情面板中找不到原生表情: {sticker.name}")


def _css_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _mark_latest_outgoing_message(page: Page) -> tuple[str, str]:
    anchor = secrets.token_hex(8)
    latest = page.locator(LATEST_OUTGOING_MESSAGE).first
    if not await latest.count():
        return anchor, ""

    content = latest.locator('[data-e2e="msg-item-content"]').first
    before_content = await content.inner_html() if await content.count() else await latest.inner_html()
    await latest.evaluate(
        "(element, value) => element.setAttribute('data-douyin-sender-anchor', value)",
        anchor,
    )
    return anchor, before_content


async def _click_and_confirm_sticker(page: Page, item, before: tuple[str, str], name: str) -> None:
    resource_key = await _sticker_resource_key(item)
    await item.click(force=True)
    await _confirm_sticker_sent(page, before, name, resource_key)


async def _sticker_resource_key(item) -> str:
    src = await item.get_attribute("src")
    if not src:
        image = item.locator("img").first
        if await image.count():
            src = await image.get_attribute("src")
    if not src:
        return ""
    return urlsplit(src).path.rsplit("/", 1)[-1]


async def _confirm_sticker_sent(
    page: Page,
    before: tuple[str, str],
    name: str,
    resource_key: str = "",
) -> None:
    anchor, before_content = before
    try:
        await page.wait_for_function(
            """([selector, anchor, previousContent, expectedResource]) => {
                const message = document.querySelector(selector);
                if (!message) return false;
                const content = message.querySelector('[data-e2e="msg-item-content"]') || message;
                const isNewMessage =
                    message.getAttribute('data-douyin-sender-anchor') !== anchor ||
                    content.innerHTML !== previousContent;
                if (!isNewMessage) return false;
                if (!expectedResource) return true;
                const images = [...content.querySelectorAll('img')];
                return images.some(image => (image.src || '').includes(expectedResource)) || images.length > 0;
            }""",
            arg=[LATEST_OUTGOING_MESSAGE, anchor, before_content, resource_key],
            timeout=15_000,
        )
        await page.wait_for_timeout(3_000)
        latest = page.locator(LATEST_OUTGOING_MESSAGE).first
        for selector in STICKER_FAILURE_MARKERS:
            marker = latest.locator(selector).first
            if await marker.count() and await marker.is_visible():
                raise PageOperationError(f"原生表情“{name}”发送失败，页面提示可以重试")
    except PageOperationError:
        raise
    except Exception as exc:
        raise PageOperationError(f"原生表情“{name}”已点击，但没有检测到新的已发送消息") from exc
    finally:
        await _clear_confirmation_anchors(page)


async def _clear_confirmation_anchors(page: Page) -> None:
    anchors = page.locator(f"[{STICKER_CONFIRM_ANCHOR}]")
    try:
        await anchors.evaluate_all(
            "elements => elements.forEach(element => element.removeAttribute('data-douyin-sender-anchor'))"
        )
    except Exception:
        pass
