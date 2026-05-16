# 🎓 CQU-Final-Score Notifier

> **底层逻辑**：针对重庆大学教务系统查询延迟的痛点，构建自动化轮询与即时邮件通知系统。实现从“人等数据”到“数据找人”的交互范式转移。

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/Jacknie666/CQU_FINAL_SCORE)

---

## 🚀 项目抓手 (Highlights)

*   **实时侦听**：采用高频率轮询机制，第一时间捕获教务系统成绩发布状态。
*   **多维分发**：支持 SMTP 邮件协议，实现成绩信息的跨端即时触达。
*   **鲁棒性设计**：内置异常处理逻辑，应对教务系统高负载下的网络抖动。
*   **私密安全**：核心凭证本地配置，确保教务账号安全。

---

## 🛠 技术实现 (Implementation)

1.  **Session 持久化**：模拟登录并维护 Cookie 池。
2.  **数据清洗**：使用 `BeautifulSoup` 提取成绩表格，对比本地快照。
3.  **状态机闭环**：检测到变化即触发邮件任务，并更新本地记录。

---

## 📦 部署指南 (Deployment)

1.  **安装依赖**：
    ```bash
    pip install requests beautifulsoup4
    ```
2.  **配置参数**：
    编辑 `config.json`，填入教务账号及 SMTP 配置。
3.  **常驻运行**：
    建议在服务器或本地使用 `nohup` 或 `screen` 挂机。

---

## 📈 演进方向 (Roadmap)
- [x] 基本成绩轮询与邮件推送
- [ ] 微信推送（集成 Server酱/PushPlus）
- [ ] 自动计算绩点与班级排名预估
- [ ] 适配全校选修课余量监测

---

## 🤝 参与共建
如果你也对改善 CQU 学习体验感兴趣，欢迎贡献代码或提供**场景优化**建议。

*Created by Jacknie666 | 重庆大学金融管理 & CS 双修*
