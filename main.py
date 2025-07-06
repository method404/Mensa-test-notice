#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
    print("오류: TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHANNEL_ID 환경 변수가 설정 오류")
    exit(1)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    data = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        print(f"텔레그램 메시지 전송 성공: {CHANNEL_ID}")
        return True
    except Exception as e:
        print(f"텔레그램 메시지 전송 실패 (채널 {CHANNEL_ID}): {e}")
        return False

def parse_test_date(date_text):
    pattern = r'(\d{4})년\s+(\d{2})월\s+(\d{2})일\s+\[(.*?)\]'
    match = re.search(pattern, date_text)
    
    if match:
        year, month, day, location = match.groups()
        test_date = datetime(int(year), int(month), int(day))
        return {
            "date": test_date,
            "location": location,
            "original_text": date_text
        }
    return None

def parse_application_period(period_text):
    pattern = r'(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})'
    match = re.search(pattern, period_text)
    
    if match:
        start_year, start_month, start_day, end_year, end_month, end_day = match.groups()
        start_date = datetime(int(start_year), int(start_month), int(start_day))
        end_date = datetime(int(end_year), int(end_month), int(end_day))
        return {
            "start_date": start_date,
            "end_date": end_date,
            "original_text": period_text
        }
    return None

def get_mensa_test_schedules():
    url = "https://www.mensakorea.org/bbs/board.php?bo_table=test"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        upcoming_tests = []
        test_rows = soup.select('tr[height="29"]')
        
        for row in test_rows:
            test_link = row.select_one('td a')
            if not test_link:
                continue
                
            text = test_link.get_text().strip()
            test_info = parse_test_date(text)
            if not test_info:
                continue
                
            href = test_link.get('href', '')
            if href and isinstance(href, str):
                if "../" in href:
                    href = href.replace("../", "/")
                test_info["link"] = f"https://www.mensakorea.org{href}"
            
            period_cell = row.select('td.c.f_ver11')[1] if len(row.select('td.c.f_ver11')) > 1 else None
            if period_cell:
                period_text = period_cell.get_text().strip()
                period_info = parse_application_period(period_text)
                if period_info:
                    test_info["application_start"] = period_info["start_date"]
                    test_info["application_end"] = period_info["end_date"]
                    test_info["application_period"] = period_text
            
            status_cell = row.select_one('td img')
            src_attr = status_cell.get('src') if status_cell else None
            status_is_closed = isinstance(src_attr, str) and 'icon_end' in src_attr
            
            if status_is_closed:
                test_info["status"] = "마감"
            else:
                test_info["status"] = "접수예정" if test_info.get("application_start", datetime.now() + timedelta(days=1)) > datetime.now() else "접수중"
            
            upcoming_tests.append(test_info)
        
        print(f"총 {len(upcoming_tests)}개의 테스트 일정을 찾았습니다.")
        return upcoming_tests
    
    except Exception as e:
        print(f"멘사 테스트 일정 스크래핑 실패: {e}")
        return []

def check_upcoming_tests():
    """오늘 이후의 테스트 일정 확인"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    test_schedules = get_mensa_test_schedules()
    upcoming_tests = [test for test in test_schedules if test["date"] >= today]
    
    if upcoming_tests:
        # 날짜 기준으로 정렬
        upcoming_tests.sort(key=lambda x: x["date"])
        
        # 알림 메시지 생성
        message = "<b>🧠 멘사 코리아 테스트 알림</b>\n\n"
        message += "다음 일정의 멘사 테스트가 예정되어 있습니다:\n\n"
        
        for idx, test in enumerate(upcoming_tests, 1):
            date_str = test["date"].strftime("%Y년 %m월 %d일")
            location = test["location"]
            link = test["link"]
            status = test.get("status", "")
            
            test_days_left = (test["date"] - today).days
            test_d_day = f"D-{test_days_left}" if test_days_left > 0 else "D-Day"
            
            status_msg = ""
            if status == "마감":
                status_msg = f"[접수마감, 테스트 {test_d_day}]"
            elif "application_start" in test and "application_end" in test:
                app_start = test["application_start"]
                app_end = test["application_end"]
                
                if app_start > today:  # 접수 시작 전
                    start_days_left = (app_start - today).days
                    status_msg = f"[접수 시작 D-{start_days_left}]"
                elif app_end >= today:  # 접수 진행 중
                    end_days_left = (app_end - today).days
                    status_msg = f"[접수중, 마감 D-{end_days_left}]"
                else:  # 접수 마감
                    status_msg = f"[접수마감, 테스트 {test_d_day}]"
            
            message += f"{idx}. <b>{date_str} [{location}] \n {status_msg}\n</b>"
            if "application_period" in test:
                message += f"   접수기간: {test['application_period']}\n"
            message += f"   <a href='{link}'>상세 정보 보기</a>\n\n"
        
        message += "자세한 내용은 멘사 코리아 홈페이지를 참고하세요."
        
        send_telegram_message(message)
        
        return upcoming_tests
    else:
        message = "현재 예정된 테스트 일정이 없습니다."
        send_telegram_message(message)
        print(message)
        return []

def main():
    """메인 함수"""
    print("멘사 테스트 일정 확인 시작")
    
    try:
        upcoming_tests = check_upcoming_tests()
        if upcoming_tests:
            print(f"{len(upcoming_tests)}개의 예정된 테스트 일정 알림을 전송했습니다.")
    except Exception as e:
        print(f"실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
