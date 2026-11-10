#!/usr/bin/env bash
# ==============================================================================
# HANOI IT JOB RADAR - TRÌNH ĐIỀU KHIỂN BẬT / TẮT BOT
# ==============================================================================

# Xác định thư mục gốc của bot
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR" || exit 1

PID_FILE="$APP_DIR/data/bot.pid"
LOG_FILE="$APP_DIR/logs/app.log"
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

# Tự động nhận diện Python (ưu tiên venv)
if [ -f "$APP_DIR/venv/bin/python" ]; then
    PYTHON="$APP_DIR/venv/bin/python"
elif [ -f "$APP_DIR/venv/bin/python3" ]; then
    PYTHON="$APP_DIR/venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# Hàm lấy PID của bot đang chạy
get_bot_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi
    # Tìm kiếm dự phòng theo tiến trình
    local proc_pid
    proc_pid=$(pgrep -f "python.*main.py" | head -n 1)
    if [ -n "$proc_pid" ]; then
        echo "$proc_pid" > "$PID_FILE"
        echo "$proc_pid"
        return 0
    fi
    return 1
}

# Hàm kiểm tra trạng thái
check_status() {
    local pid
    pid=$(get_bot_pid)
    if [ -n "$pid" ]; then
        local ram_kb ram_mb cpu uptime
        ram_kb=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')
        cpu=$(ps -o %cpu= -p "$pid" 2>/dev/null | tr -d ' ')
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
        if [ -n "$ram_kb" ]; then
            ram_mb=$(awk "BEGIN {printf \"%.1f\", $ram_kb/1024}")
        else
            ram_mb="N/A"
        fi
        echo "🟢 Trạng thái: ĐANG CHẠY"
        echo "   • PID:         $pid"
        echo "   • RAM sử dụng: ${ram_mb} MB"
        echo "   • CPU:         ${cpu}%"
        echo "   • Thời gian:   $uptime"
        return 0
    else
        echo "🔴 Trạng thái: ĐÃ TẮT"
        return 1
    fi
}

# Hàm bật bot
start_bot() {
    local pid
    pid=$(get_bot_pid)
    if [ -n "$pid" ]; then
        echo "⚠️  Bot ĐANG CHẠY RỒI! (PID: $pid)"
        echo "   Dùng './bot.sh logs' để xem hoạt động hoặc './bot.sh restart' để khởi động lại."
        return 0
    fi

    echo "🚀 Đang khởi động Hanoi IT Job Radar Bot..."
    nohup "$PYTHON" main.py >> "$LOG_FILE" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    sleep 2
    if kill -0 "$new_pid" 2>/dev/null; then
        echo "=========================================================="
        echo "  ✅ BẬT BOT THÀNH CÔNG!"
        echo "  • Tiến trình PID: $new_pid"
        echo "  • Bot đang chạy ngầm 24/7."
        echo "  • Xem log chạy:     ./bot.sh logs"
        echo "  • Tắt bot khi cần:  ./bot.sh stop"
        echo "=========================================================="
    else
        echo "❌ Khởi động bot thất bại! Kiểm tra 15 dòng log gần nhất:"
        tail -n 15 "$LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# Hàm tắt bot
stop_bot() {
    local pid
    pid=$(get_bot_pid)
    if [ -z "$pid" ]; then
        echo "[INFO] Hanoi IT Job Radar service is currently stopped."
        rm -f "$PID_FILE"
        return 0
    fi

    echo "[INFO] Stopping Hanoi IT Job Radar service (PID: $pid)..."
    kill "$pid" 2>/dev/null

    # Chờ tối đa 8 giây để tắt êm
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 8 ]; do
        sleep 1
        count=$((count + 1))
        echo -n "."
    done
    echo ""

    # Nếu vẫn chưa tắt thì ép dừng
    if kill -0 "$pid" 2>/dev/null; then
        echo "[WARN] Process did not terminate gracefully. Sending SIGKILL..."
        kill -9 "$pid" 2>/dev/null
    fi

    # Dọn dẹp tiến trình Playwright Chromium nếu có
    pkill -9 -f "chrome-linux/chrome" 2>/dev/null || true
    pkill -9 -f "chromium" 2>/dev/null || true
    rm -f "$PID_FILE"

    echo "=========================================================="
    echo "  [SUCCESS] Hanoi IT Job Radar service stopped."
    echo "  • Status: STOPPED"
    echo "  • To start again: ./bot.sh start"
    echo "=========================================================="
}

# Hàm khởi động lại bot
restart_bot() {
    echo "🔄 Đang khởi động lại bot..."
    stop_bot
    sleep 1
    start_bot
}

# Hàm xem log trực tiếp
show_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo "⚠️ Chưa có file log tại $LOG_FILE"
        return 1
    fi
    echo "📄 Đang theo dõi log trực tiếp (Nhấn Ctrl + C để thoát)..."
    echo "----------------------------------------------------------"
    tail -n 50 -f "$LOG_FILE"
}

# Hàm tạo shortcut toàn hệ thống
install_shortcut() {
    if [ "$EUID" -ne 0 ]; then
        echo "⚠️  Cần quyền root (sudo) để cài lệnh toàn hệ thống."
        echo "   Vui lòng chạy: sudo ./bot.sh install"
        return 1
    fi
    # Xóa symlink cũ nếu có để tránh xung đột
    rm -f /usr/local/bin/bot /usr/local/bin/crawlerbot
    ln -sf "$APP_DIR/bot.sh" /usr/local/bin/crawlerbot
    chmod +x "$APP_DIR/bot.sh" /usr/local/bin/crawlerbot
    echo "=========================================================="
    echo "  ✅ ĐÃ CÀI ĐẶT LỆNH 'crawlerbot' TOÀN HỆ THỐNG!"
    echo "  Từ bây giờ, ở bất kỳ đâu trên VPS bạn chỉ cần gõ:"
    echo "    • crawlerbot          -> Mở menu điều khiển"
    echo "    • crawlerbot start    -> Bật bot"
    echo "    • crawlerbot stop     -> Tắt bot"
    echo "    • crawlerbot status   -> Xem trạng thái"
    echo "    • crawlerbot logs     -> Xem log"
    echo "=========================================================="
}

# Menu tương tác khi không truyền tham số
interactive_menu() {
    while true; do
        clear 2>/dev/null || true
        echo "=========================================================="
        echo "       🤖 HANOI IT JOB RADAR - ĐIỀU KHIỂN BOT             "
        echo "=========================================================="
        check_status
        echo "----------------------------------------------------------"
        echo "  [1] 🚀 BẬT BOT (Khởi động bot)"
        echo "  [2] 🛑 TẮT BOT (Dừng bot)"
        echo "  [3] 🔄 Khởi động lại bot"
        echo "  [4] 📄 Xem log cào việc thời gian thực"
        echo "  [5] 📊 Kiểm tra trạng thái chi tiết"
        echo "  [6] ⚡ Cài đặt phím tắt 'crawlerbot' toàn hệ thống"
        echo "  [0] 🚪 Thoát"
        echo "=========================================================="
        read -r -p "👉 Nhập lựa chọn của bạn [0-6]: " choice
        echo ""

        case "$choice" in
            1)
                start_bot
                read -r -p "Nhấn Enter để quay lại menu..." _
                ;;
            2)
                stop_bot
                read -r -p "Nhấn Enter để quay lại menu..." _
                ;;
            3)
                restart_bot
                read -r -p "Nhấn Enter để quay lại menu..." _
                ;;
            4)
                show_logs
                ;;
            5)
                check_status
                read -r -p "Nhấn Enter để quay lại menu..." _
                ;;
            6)
                install_shortcut
                read -r -p "Nhấn Enter để quay lại menu..." _
                ;;
            0|q|Q)
                echo "Tạm biệt!"
                exit 0
                ;;
            *)
                echo "Lựa chọn không hợp lệ!"
                sleep 1
                ;;
        esac
    done
}

# Xử lý tham số truyền vào
case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        check_status
        ;;
    logs|log)
        show_logs
        ;;
    install)
        install_shortcut
        ;;
    help|--help|-h)
        echo "Sử dụng:"
        echo "  ./bot.sh           -> Mở Menu điều khiển trực quan"
        echo "  ./bot.sh start     -> Bật bot chạy ngầm"
        echo "  ./bot.sh stop      -> Tắt bot và giải phóng RAM"
        echo "  ./bot.sh restart   -> Khởi động lại bot"
        echo "  ./bot.sh status    -> Kiểm tra trạng thái bot"
        echo "  ./bot.sh logs      -> Xem log trực tiếp"
        echo "  ./bot.sh install   -> Cài lệnh tắt 'crawlerbot' vào hệ thống"
        ;;
    "")
        interactive_menu
        ;;
    *)
        echo "Lệnh không hợp lệ: '$1'. Gõ './bot.sh help' để xem hướng dẫn."
        exit 1
        ;;
esac
