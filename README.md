# 抖音自动续火花 - GitHub Actions 教程

使用 GitHub Actions 定时运行本项目，不需要服务器长期在线。

> `DOUYIN_COOKIE` 是登录凭证，请只保存在 GitHub Secrets 中，不要提交到仓库或公开分享。

## 1. Fork 并启用 Actions

先 Fork 本仓库，然后进入自己 Fork 后的仓库：
![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/DKPd0GVi.webp)

`Actions` → 启用工作流。

## 2. 获取抖音 Cookie

1. 在电脑浏览器登录抖音网页版，并确认私信页面可以正常打开。
2. 使用 Cookie-Editor 等工具导出当前站点 Cookie。
3. [Cookie-Editor工具地址](https://chromewebstore.google.com/detail/hlkenndednhfkekhgcdicdfddnkalmdm?utm_source=item-share-cb)
  ![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/STZqIxDn.webp)
4. 导出格式选择 **JSON**，复制完整的 JSON 数组。
![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/1rilVYmK.webp)
![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/QKQHfndn.webp)
格式类似：

```json
[
  {
    "name": "xxx",
    "value": "xxx",
    "domain": ".douyin.com",
    "path": "/"
  }
]
```

必须是完整的 `[ ... ]` 数组，不是 `name=value` 形式。

## 3. 配置 GitHub Secrets

进入：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/aiPBHuxJ.webp)
![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/BKtXckyQ.webp)

需要添加：

| Secret | 内容 | 必需 |
| --- | --- | --- |
| `DOUYIN_COOKIE` | 上一步导出的 Cookie JSON | 是 |
| `DOUYIN_CONFIG` | 完整发送配置 JSON | 是 |
| `DINGTALK_WEBHOOK` | 钉钉机器人 Webhook | 否 |
| `DINGTALK_SECRET` | 钉钉机器人 Secret | 否 |

钉钉通知不用就不要配置；需要使用时，两个钉钉 Secret 必须同时填写。

### DOUYIN_CONFIG 示例

支持普通文字和抖音原生表情：

```json
{
  "friends": ["好友昵称"],
  "messages": [
    {"type": "text", "value": "续火花 ✨"},
    {"type": "sticker", "value": "比心"}
  ],
  "stickers": {
    "比心": {
      "label": "比心",
      "category": "常用",
      "fallback_index": 3
    }
  },
  "send_interval_seconds": {
    "min": 3,
    "max": 8
  },
  "prevent_duplicates": false
}
```

原生表情配置说明：

- `type: "sticker"`：发送抖音原生表情。
- `value`：对应 `stickers` 中的表情名称。
- `label`：抖音表情面板中显示的名称，程序优先按名称查找。
- `category`：表情所在分类，例如 `常用`。
- `fallback_index`：按名称找不到时使用的备用序号，从 `0` 开始。

不同账号的表情顺序可能不同，`fallback_index` 需要按自己的抖音表情面板调整。

第一次建议只配置 **1 个好友** 测试。修改好友、消息或表情时，直接更新 `DOUYIN_CONFIG` Secret 即可。

## 4. 先运行 Dry Run

进入：

`Actions` → `Send Douyin Messages` → `Run workflow`

第一次把：

```text
dry_run = true
```

再运行工作流。
![image.webp](https://img.908988.xyz/file/教程/douyin-auto-fire/NLFF8g94.webp)

Dry Run 会检查登录状态和好友定位，**不会发送消息**。

如果运行失败，点进本次 Workflow Run，查看 `send` → `Run` 的日志。

## 5. 测试真实发送

Dry Run 成功后，再手动运行一次：

```text
dry_run = false
```

这次会真实发送消息。

建议仍然只保留一个测试好友，确认发送对象、文字和原生表情都正确后，再增加好友。

## 6. 定时运行

定时配置在：

```text
.github/workflows/send.yml
```

当前配置：

```yaml
schedule:
  - cron: "0 0 * * *"
    timezone: "Asia/Shanghai"
```

表示 **每天北京时间 00:00** 自动运行。

例如改成每天北京时间 08:30：

```yaml
schedule:
  - cron: "30 8 * * *"
    timezone: "Asia/Shanghai"
```

格式为：

```text
分钟 小时 * * *
```

定时触发会直接真实发送，不会自动 Dry Run。

## 7. Cookie 失效

如果日志提示登录失效或安全验证：

1. 在浏览器重新登录抖音；
2. 重新导出 Cookie JSON；
3. 更新 GitHub Secret `DOUYIN_COOKIE`；
4. 先手动运行一次 `dry_run = true`。

GitHub Actions 不会自动扫码登录，也不会绕过验证码或安全验证。

## 8. 失败日志

工作流失败时只会上传不包含会话凭据的诊断文件：

- `run.log`
- `result.json`

截图和 Playwright trace 可能包含私人聊天内容或 Cookie，只保留在 runner
的临时磁盘，不会上传为公开仓库的 Actions artifact。

失败 Artifact 保留 3 天。日志可能包含好友名称或错误上下文，请勿公开分享。

## 注意

- Cookie 和配置不要直接提交到仓库。
- 修改好友或表情配置后建议重新 Dry Run。
- 同一个账号不要同时运行多个定时器，避免重复发送。
- GitHub-hosted runner 的网络环境变化可能触发抖音安全验证。


## 友情链接

- [LINUX DO](https://linux.do/) - 新的理想型社区


## License

本项目采用 [MIT License](LICENSE)。
