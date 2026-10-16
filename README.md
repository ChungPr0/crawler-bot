# 🚀 Hanoi IT Job Radar Bot (Automation & Data Pipeline)

Hệ thống tự động cào tin tuyển dụng lập trình viên (tập trung mảng **Java / Spring Boot / Backend** cấp bậc **Intern / Fresher**) tại khu vực **Hà Nội** từ 3 nguồn dữ liệu lớn: **ITviec**, **TopCV** và **Facebook Group**, sau đó lọc thông minh và gửi thông báo tức thì qua **Discord Webhook** và **Telegram Bot**.

Dự án được thiết kế theo chuẩn **Production-grade (Clean Code, Modular Architecture, Async I/O, Error Resilient)**, sẵn sàng đóng gói Docker để vận hành 24/7 trên Ubuntu VPS.

---

## 📑 Mục lục
1. [Kiến trúc hệ thống (System Architecture)](#-kiến-trúc-hệ-thống)
2. [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
3. [Cơ chế bộ lọc thông minh (Filter Engine)](#-cơ-chế-bộ-lọc-thông-minh)
4. [Hướng dẫn chuẩn bị Token & Cookies](#-hướng-dẫn-chuẩn-bị-token--cookies)
   - [Lấy Discord Webhook](#1-lấy-discord-webhook)
   - [Tạo Telegram Bot & Lấy Chat ID](#2-tạo-telegram-bot--lấy-chat-id)
   - [Xuất Facebook Cookies](#3-xuất-facebook-cookies)
5. [Cài đặt và chạy trên máy Local](#-cài-đặt-và-chạy-local)
6. [Triển khai chạy ngầm 24/7 trên Ubuntu VPS với Docker](#-triển-khai-production-trên-ubuntu-vps-với-docker)
7. [Phương án triển khai thay thế bằng Systemd](#-phương-án-triển-khai-với-systemd-service)
8. [Quản trị, Backup & Giám sát (Monitoring)](#-quản-trị--giám-sát)

---

## 🏛️ Kiến trúc hệ thống

```
+--------------------------------------------------------------------------+
|                        SCHEDULER (APScheduler / 15m)                     |
+--------------------------------------------------------------------------+
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
 ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
 │ ITViecCrawler │           │  TopCVCrawler │           │FBGroupCrawler │
 │(httpx + BS4)  │           │ (httpx + BS4) │           │  (Playwright) │
 └───────┬───────┘           └───────┬───────┘           └───────┬───────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     ▼
                       ┌───────────────────────────┐
                       │   Filter Engine (Rules)   │
                       │ - Tech: Java/Spring/BE    │
                       │ - Level: Intern/Fresher   │
                       │ - Blacklist rejection     │
                       │ - Hanoi location check    │
                       └─────────────┬─────────────┘
                                     ▼
                       ┌───────────────────────────┐
                       │  Deduplication (SQLite)   │
                       │   Check MD5 Job ID in DB  │
                       └─────────────┬─────────────┘
                                     │ (New Job Only)
                                     ▼
                        ┌─────────────────────────┐
                        │    Notifier Manager     │
                        └────────────┬────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
         ┌─────────────────────┐           ┌─────────────────────┐
         │   Discord Webhook   │           │    Telegram Bot     │
         │ (Rich Embed Colors) │           │(HTML + Inline Button)
         └─────────────────────┘           └─────────────────────┘
```

---

## 📂 Cấu trúc thư mục

```
crawler-bot/
├── config/
│   ├── __init__.py
│   └── settings.py              # Quản lý biến môi trường với Pydantic Settings
├── crawlers/
│   ├── __init__.py
│   ├── base_crawler.py          # Lớp cơ sở: Backoff retry, xoay vòng User-Agent
│   ├── itviec_crawler.py        # Cào ITviec (HTTPX + BeautifulSoup4)
│   ├── topcv_crawler.py         # Cào TopCV (HTTPX + BeautifulSoup4)
│   └── fb_group_crawler.py      # Cào Facebook Groups (Playwright Headless + Cookies)
├── database/
│   ├── __init__.py
│   └── repository.py            # SQLite Async I/O (aiosqlite), khử trùng lặp
├── filters/
│   ├── __init__.py
│   └── filter_engine.py         # Bộ lọc Regex từ khóa, kiểm tra Blacklist & Địa điểm
├── models/
│   ├── __init__.py
│   └── job.py                   # Data Model JobItem, mã hóa MD5 hash ID, format tags
├── notifiers/
│   ├── __init__.py
│   ├── discord_notifier.py      # Bắn Rich Embed Webhook (phân màu theo nguồn)
│   ├── telegram_notifier.py     # Gửi tin nhắn định dạng HTML kèm nút mở link
│   └── notifier_manager.py      # Điều phối gửi đa kênh song song
├── utils/
│   ├── __init__.py
│   ├── logger.py                # Cấu hình Loguru: console + rotating log file
│   └── user_agents.py           # Danh sách User-Agents thực tế & header generator
├── cookies/
│   └── cookies.json.example     # File mẫu cấu trúc cookie Facebook
├── data/                        # Thư mục chứa database SQLite (volume mount)
├── logs/                        # Thư mục chứa app.log, error.log (volume mount)
├── .env.example                 # Mẫu file biến môi trường
├── .gitignore                   # Loại trừ file rác, dữ liệu nhạy cảm
├── Dockerfile                   # Dockerfile tối ưu chạy Playwright Chromium
├── docker-compose.yml           # Compose cấu hình volume, memory limit, auto restart
├── main.py                      # Điểm khởi chạy chính & Scheduler
├── requirements.txt             # Danh sách thư viện Python
├── run_bot.bat                  # Script 1-Click tự động thiết lập & chạy trên Windows
└── README.md                    # Tài liệu hướng dẫn sử dụng chi tiết
```

---

## 🎯 Cơ chế bộ lọc thông minh (Filter Engine)

Bài đăng chỉ được gửi thông báo khi thỏa mãn **toàn bộ 4 điều kiện** sau:

1. **Từ khóa chuyên môn (Bắt buộc chứa ít nhất 1 từ):**
   - `Java` (Regex `\bjava\b(?!script)` chặn bắt nhầm JavaScript)
   - `Spring`
   - `Spring Boot`
   - `Backend` / `Back-end`
   - `Backend Developer` / `Lập trình backend`
2. **Cấp bậc / Trình độ (Bắt buộc chứa ít nhất 1 từ):**
   - `Intern`, `Internship`, `Thực tập`, `Thực tập sinh`, `TTS`
   - `Fresher`, `Mới tốt nghiệp`, `Năm cuối`, `Trainee`
3. **Blacklist (Loại bỏ ngay lập tức nếu chứa bất kỳ từ nào):**
   - Mảng lệch: `Android`, `Flutter`, `React Native`
   - Rác / Khóa học: `Khóa học`, `Học phí`, `Đào tạo học viên`, `Cam kết việc làm`, `Học viên`, `Triển khai phần mềm`
4. **Địa điểm:**
   - Thuộc khu vực Hà Nội: `Hà Nội`, `HN`, `Cầu Giấy`, `Thanh Xuân`, `Đống Đa`, `Nam Từ Liêm`, `Bắc Từ Liêm`, `Ba Đình`, `Hai Bà Trưng`, `Hoàng Mai`, `Hà Đông`, `Tây Hồ`, `Long Biên`.
   - Nếu bài viết ghi rõ địa phương khác (TP.HCM, Đà Nẵng...) mà không kèm Hà Nội -> Tự động loại bỏ.

---

## 🔑 Hướng dẫn chuẩn bị Token & Cookies

### 1. Lấy Discord Webhook
1. Mở Discord > Chọn Server của bạn > Chọn kênh muốn nhận thông báo (ví dụ `#job-radar`).
2. Bấm vào icon **Bánh răng (Edit Channel)** > **Integrations** > **Webhooks** > **New Webhook**.
3. Đặt tên (ví dụ: `Hanoi Job Bot`) và copy **Webhook URL**.
4. Dán vào file `.env`:
   ```env
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
   ENABLE_DISCORD=true
   ```

### 2. Tạo Telegram Bot & Lấy Chat ID
1. Mở Telegram, tìm kiếm **`@BotFather`** > Gửi lệnh `/newbot`.
2. Đặt tên Bot và username (kết thúc bằng `_bot`). Lưu lại **HTTP API Token** (ví dụ `712345678:AAH...`).
3. Lấy **Chat ID**:
   - Gửi bất kỳ 1 tin nhắn (ví dụ: `hi`) cho con Bot bạn vừa tạo.
   - Tìm kiếm bot **`@userinfobot`** trên Telegram và bấm `/start`, bot sẽ trả về số `Id` của bạn (ví dụ: `987654321`).
   - *(Nếu muốn gửi vào Group: Thêm bot vào Group và cấp quyền Admin, sau đó dùng bot `@getidsbot` để lấy Group Chat ID có dạng số âm `-100xxxxxxxxx`)*.
4. Dán vào `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=712345678:AAHxxxxxxxxxxxxxxxxxxxxxx
   TELEGRAM_CHAT_ID=987654321
   ENABLE_TELEGRAM=true
   ```

### 3. Xuất Facebook Cookies
Để Playwright đọc được bài viết trong các Group Facebook:
1. Cài đặt tiện ích mở rộng [Cookie-Editor](https://cookie-editor.com/) trên trình duyệt Chrome/Firefox.
2. Đăng nhập vào tài khoản Facebook trên trình duyệt (khuyến nghị dùng nick clone phụ để an toàn).
3. Bấm vào icon **Cookie-Editor** > Chọn nút **Export** > Chọn **Export as JSON**.
4. Tạo file `cookies/cookies.json` trong thư mục dự án và dán toàn bộ nội dung JSON vừa copy vào.

---

## 💻 Cài đặt và chạy Local

### Yêu cầu:
- Python 3.10 trở lên.

### Các bước:
```bash
# 1. Clone hoặc tải mã nguồn về máy
cd crawler-bot

# 2. Tạo môi trường ảo (virtual environment)
python -m venv venv

# Kích hoạt trên Linux/macOS:
source venv/bin/activate
# Kích hoạt trên Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# 3. Cài đặt dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Cài đặt Chromium cho Playwright
playwright install chromium

# 5. Cấu hình biến môi trường
cp .env.example .env
# Chỉnh sửa file .env với Discord Webhook & Telegram Token của bạn

# 6. Khởi chạy hệ thống chính
python main.py
# (Hoặc trên Windows chỉ cần chạy trực tiếp file: .\run_bot.bat)
```

---

## 🐧 Triển khai Production trên Ubuntu VPS với Docker

Đây là phương pháp triển khai chuẩn production, an toàn, ổn định và tự động khôi phục sau sự cố.

### Bước 1: Cài đặt Docker & Docker Compose trên Ubuntu VPS
Nếu VPS mới chưa có Docker, hãy chạy các lệnh sau:
```bash
# Cập nhật hệ thống
sudo apt update && sudo apt upgrade -y

# Cài đặt Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Cài đặt Docker Compose Plugin
sudo apt install -y docker-compose-plugin

# Cấp quyền cho user hiện tại (không cần gõ sudo mỗi lần)
sudo usermod -aG docker $USER
newgrp docker

# Kiểm tra phiên bản
docker --version
docker compose version
```

### Bước 2: Đưa mã nguồn lên VPS
Bạn có thể dùng `git clone` hoặc `scp` từ máy local:
```bash
# Ví dụ tạo thư mục trên VPS
mkdir -p /opt/crawler-bot
cd /opt/crawler-bot

# Copy toàn bộ code vào thư mục này
```

### Bước 3: Tạo file cấu hình `.env` và `cookies.json`
```bash
# Tạo file .env từ mẫu
cp .env.example .env

# Chỉnh sửa thông số
nano .env
```
*(Điền `DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

Đặt file cookie Facebook (nếu dùng):
```bash
mkdir -p cookies
nano cookies/cookies.json
# Dán mã JSON cookies và lưu lại (Ctrl+O, Enter, Ctrl+X)
```

### Bước 4: Build và khởi chạy Docker Compose ngầm 24/7
```bash
# Build image và khởi động ngầm (detached mode)
docker compose up -d --build
```

### Bước 5: Kiểm tra trạng thái & Nhật ký hoạt động
```bash
# Xem trạng thái container
docker compose ps

# Xem log thời gian thực
docker compose logs -f --tail=100

# Hoặc xem trực tiếp file log đã mount ra ngoài VPS
tail -f logs/app.log
```

### Các lệnh quản trị thông dụng:
```bash
# Dừng bot:
docker compose down

# Khởi động lại bot:
docker compose restart

# Cập nhật code mới sau khi sửa đổi:
docker compose up -d --build
```

---

## ⚙️ Phương án triển khai với Systemd Service (Không dùng Docker)

Nếu VPS của bạn có cấu hình quá nhỏ (dưới 1GB RAM) hoặc không muốn dùng Docker:

1. Cài đặt Python 3.10 và Chromium:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-venv
   cd /opt/crawler-bot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install --with-deps chromium
   ```

2. Tạo file cấu hình dịch vụ Systemd:
   ```bash
   sudo nano /etc/systemd/system/job-radar.service
   ```

3. Dán nội dung sau vào:
   ```ini
   [Unit]
   Description=Hanoi IT Job Radar Automation Bot
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/crawler-bot
   EnvironmentFile=/opt/crawler-bot/.env
   ExecStart=/opt/crawler-bot/venv/bin/python /opt/crawler-bot/main.py
   Restart=always
   RestartSec=15

   [Install]
   WantedBy=multi-user.target
   ```

4. Kích hoạt và khởi động dịch vụ:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable job-radar
   sudo systemctl start job-radar

   # Kiểm tra trạng thái:
   sudo systemctl status job-radar

   # Xem log:
   journalctl -u job-radar -f
   ```

---

## 🛡️ Quản trị & Giám sát

1. **Khử trùng lặp (Deduplication):**
   - File cơ sở dữ liệu `data/jobs.db` được lưu ngoài máy chủ thông qua volume mount, đảm bảo không bao giờ bị mất bài đăng cũ ngay cả khi build lại Docker image.
   - Mỗi bài đăng được định danh duy nhất bằng mã băm `MD5(source:url)` để ngăn chặn tuyệt đối việc spam lặp tin.

2. **Xoay vòng Log (Log Rotation):**
   - Thư viện `Loguru` tự động xoay vòng file `logs/app.log` khi đạt kích cỡ 10MB và nén zip, lưu trữ trong 14 ngày.
   - Docker Container cũng được giới hạn log tối đa 3 file x 10MB để không gây tràn ổ cứng VPS.

3. **Giới hạn tài nguyên (Resource Constraints):**
   - Cấu hình trong `docker-compose.yml` giới hạn tối đa 1GB RAM và 1.0 CPU Core để bot vận hành mượt mà mà không ảnh hưởng tới các dịch vụ khác đang chạy trên cùng VPS.

