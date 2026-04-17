#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
PID_FILE="${RUNTIME_DIR}/javscraper.pid"
LOG_FILE="${RUNTIME_DIR}/javscraper.log"
ENV_FILE="${RUNTIME_DIR}/javscraper.env"

mkdir -p "${RUNTIME_DIR}"

resolve_python() {
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    printf '%s\n' "${REPO_ROOT}/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  printf '%s\n' "python3"
}

PYTHON_BIN="$(resolve_python)"

is_running() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  if ps -p "${pid}" >/dev/null 2>&1; then
    return 0
  fi
  rm -f "${PID_FILE}"
  return 1
}

show_current_config() {
  if [[ -f "${ENV_FILE}" ]]; then
    echo "当前启动配置:"
    cat "${ENV_FILE}"
  else
    echo "当前没有保存的启动配置。"
  fi
}

status_app() {
  if is_running; then
    local pid
    pid="$(cat "${PID_FILE}")"
    echo "javScraper26 正在运行"
    echo "PID: ${pid}"
    echo "日志: ${LOG_FILE}"
    show_current_config
  else
    echo "javScraper26 当前未运行"
  fi
}

stop_app() {
  if ! is_running; then
    echo "javScraper26 当前未运行，无需停止。"
    return 0
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  echo "正在停止 javScraper26 (PID ${pid}) ..."
  kill "${pid}" >/dev/null 2>&1 || true

  local waited=0
  while ps -p "${pid}" >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if (( waited >= 10 )); then
      echo "进程未在 10 秒内退出，尝试强制结束..."
      kill -9 "${pid}" >/dev/null 2>&1 || true
      break
    fi
  done

  rm -f "${PID_FILE}"
  echo "已停止。"
}

prompt_mode() {
  local choice
  echo
  echo "选择启动模式:"
  echo "  1) selector   根路径进入模式选择页"
  echo "  2) webui      直接进入普通 WebUI"
  echo "  3) service    直接进入 Emby 服务模式"
  read -r -p "请输入选项 [1]: " choice
  case "${choice:-1}" in
    1) APP_MODE="" ;;
    2) APP_MODE="webui" ;;
    3) APP_MODE="service" ;;
    *) echo "无效选项，默认使用 selector"; APP_MODE="" ;;
  esac
}

prompt_port() {
  local default_port=""
  if [[ "${APP_MODE}" == "service" ]]; then
    default_port="8765"
  fi
  echo
  read -r -p "端口号（留空则使用默认/随机端口） [${default_port}]: " APP_PORT
  APP_PORT="${APP_PORT:-${default_port}}"
}

prompt_browser() {
  local browser_choice
  echo
  if [[ "${APP_MODE}" == "service" ]]; then
    read -r -p "是否自动打开浏览器？ [n]: " browser_choice
    browser_choice="${browser_choice:-n}"
  else
    read -r -p "是否自动打开浏览器？ [y]: " browser_choice
    browser_choice="${browser_choice:-y}"
  fi
  case "${browser_choice}" in
    y|Y|yes|YES) DISABLE_BROWSER="0" ;;
    *) DISABLE_BROWSER="1" ;;
  esac
}

write_env_file() {
  {
    printf 'PYTHON_BIN=%s\n' "${PYTHON_BIN}"
    printf 'JAVSCRAPER_MODE=%s\n' "${APP_MODE}"
    printf 'JAVSCRAPER_PORT=%s\n' "${APP_PORT}"
    printf 'JAVSCRAPER_DISABLE_BROWSER=%s\n' "${DISABLE_BROWSER}"
  } > "${ENV_FILE}"
}

start_app() {
  if is_running; then
    echo "javScraper26 已在运行。"
    status_app
    return 0
  fi

  prompt_mode
  prompt_port
  prompt_browser
  write_env_file

  echo
  echo "正在启动 javScraper26 ..."
  (
    cd "${REPO_ROOT}" || exit 1
    export PYTHONUNBUFFERED=1
    if [[ -n "${APP_MODE}" ]]; then
      export JAVSCRAPER_MODE="${APP_MODE}"
    else
      unset JAVSCRAPER_MODE
    fi
    if [[ -n "${APP_PORT}" ]]; then
      export JAVSCRAPER_PORT="${APP_PORT}"
    else
      unset JAVSCRAPER_PORT
    fi
    export JAVSCRAPER_DISABLE_BROWSER="${DISABLE_BROWSER}"
    nohup "${PYTHON_BIN}" app.py >> "${LOG_FILE}" 2>&1 &
    echo $! > "${PID_FILE}"
  )

  sleep 1
  if is_running; then
    local pid
    pid="$(cat "${PID_FILE}")"
    echo "启动成功，PID: ${pid}"
    echo "日志文件: ${LOG_FILE}"
    show_current_config
  else
    echo "启动失败，请检查日志: ${LOG_FILE}"
    return 1
  fi
}

restart_app() {
  stop_app
  start_app
}

tail_logs() {
  touch "${LOG_FILE}"
  echo "正在查看日志，按 Ctrl+C 返回菜单。"
  tail -n 80 -f "${LOG_FILE}"
}

print_header() {
  echo
  echo "=============================="
  echo " javScraper26 交互管理脚本"
  echo " 仓库: ${REPO_ROOT}"
  echo " Python: ${PYTHON_BIN}"
  echo "=============================="
}

main_menu() {
  local choice
  while true; do
    print_header
    echo "1) 启动"
    echo "2) 停止"
    echo "3) 重启"
    echo "4) 状态"
    echo "5) 查看日志"
    echo "6) 查看当前配置"
    echo "0) 退出"
    echo
    read -r -p "请选择操作 [4]: " choice
    case "${choice:-4}" in
      1) start_app ;;
      2) stop_app ;;
      3) restart_app ;;
      4) status_app ;;
      5) tail_logs ;;
      6) show_current_config ;;
      0) exit 0 ;;
      *) echo "无效选项，请重新输入。" ;;
    esac
    echo
    read -r -p "按回车继续..." _
  done
}

main_menu
