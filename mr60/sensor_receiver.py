#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MR60BHA2 mmWave 레이더 센서 데이터 수신기 (sensor_receiver.py)

이 프로그램은 `sensor_simulator.py` 또는 실제 하드웨어 센서(FTDI 모듈 등으로 연결된)로부터
전송되는 바이너리 스트림 데이터를 읽어들여 프로토콜 규칙에 따라 파싱 및 출력합니다.

[사용방법]
1. 먼저 다른 터미널에서 `python3 sensor_simulator.py`를 실행합니다.
2. 이 터미널에서 `python3 sensor_receiver.py`를 실행하여 실시간 파싱 결과를 확인합니다.
"""

import sys
import time
import socket

# ANSI 색상 코드
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

class MR60BHA2Receiver:
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.buffer = bytearray()
        
        # 수집된 최신 생체 정보 상태
        self.presence = "대기중..."
        self.motion_state = "대기중..."
        self.amplitude = 0
        self.heart_rate = 0
        self.breath_rate = 0
        self.distance = 0.0

    def parse_frame(self, frame):
        """MR60BHA2 수신 바이트 프레임 해석기"""
        ctrl = frame[2]
        cmd = frame[3]
        length = (frame[4] << 8) | frame[5]
        data = frame[6:6+length]
        
        # 1. 인체 존재 보고 (Control: 0x80)
        if ctrl == 0x80:
            if cmd == 0x01:
                self.presence = "감지됨 (Someone Here)" if data[0] == 1 else "없음 (No One)"
            elif cmd == 0x02:
                motion_map = {0: "정지/동작없음", 1: "미세 움직임(정지 존재)", 2: "활발한 움직임"}
                self.motion_state = motion_map.get(data[0], f"알수없음 ({data[0]})")
            elif cmd == 0x03:
                self.amplitude = data[0]
            elif cmd == 0x04:
                dist_cm = (data[0] << 8) | data[1]
                self.distance = dist_cm / 100.0
                
        # 2. 호흡 수치 보고 (Control: 0x81)
        elif ctrl == 0x81:
            if cmd == 0x01:
                self.breath_rate = data[0]
                
        # 3. 심박 수치 보고 (Control: 0x85)
        elif ctrl == 0x85:
            if cmd == 0x02:
                self.heart_rate = data[0]
                
        # 4. 시스템 패킷 보고 (Control: 0x01)
        elif ctrl == 0x01:
            if cmd == 0x01:
                # 하트비트 생존 보고
                pass

        self.print_dashboard(frame)

    def print_dashboard(self, raw_frame):
        """터미널에 계측 결과 테이블과 수신된 가공되지 않은 HEX 원시 바이트 출력"""
        hex_str = " ".join(f"{b:02X}" for b in raw_frame)
        
        # 터미널 화면 갱신을 위해 윗줄로 이동
        sys.stdout.write("\033[H\033[J") # ANSI 홈 이동 & 화면 소거
        sys.stdout.flush()
        
        print(f"{BOLD}{MAGENTA}====================================================={RESET}")
        print(f"{BOLD}{MAGENTA}        MR60BHA2 mmWave 수집기 (Receiver Client)      {RESET}")
        print(f"{BOLD}{MAGENTA}====================================================={RESET}")
        print(f" * 접속 대상: {YELLOW}{self.host}:{self.port}{RESET}")
        print(f"-----------------------------------------------------")
        print(f" [실시간 디코딩 완료 생체 지표]")
        
        p_color = GREEN if "감지됨" in self.presence else RED
        print(f"  - 인체 존재 여부: {p_color}{self.presence}{RESET}")
        print(f"  - 신체 활동 상태: {CYAN}{self.motion_state}{RESET}")
        print(f"  - 신체 활동 세기: {self.amplitude} / 100")
        
        hr_val = f"{RED}{self.heart_rate} bpm{RESET}" if self.heart_rate > 0 else f"{WHITE}측정중...{RESET}"
        print(f"  - 실시간 심박수: {BOLD}{hr_val}")
        
        br_val = f"{BLUE}{self.breath_rate} rpm{RESET}" if self.breath_rate > 0 else f"{WHITE}측정중...{RESET}"
        print(f"  - 실시간 호흡수: {BOLD}{br_val}")
        print(f"  - 타겟과의 거리: {self.distance:.2f} m")
        print(f"-----------------------------------------------------")
        print(f" [가장 최근 수신된 HEX 프레임]")
        print(f"  {YELLOW}{hex_str}{RESET}")
        print(f"{MAGENTA}====================================================={RESET}")
        print(" Ctrl+C 를 누르면 수신기가 종료됩니다.")

    def run(self):
        print(f"{YELLOW}[클라이언트] 시뮬레이터 서버 연결 시도 중 ({self.host}:{self.port})...{RESET}")
        
        # TCP 소켓 연결
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self.host, self.port))
            print(f"{GREEN}[성공] 연결되었습니다! 원시 데이터를 파싱합니다.{RESET}")
            time.sleep(1)
        except Exception as e:
            print(f"{RED}[오류] 서버 연결에 실패했습니다: {e}{RESET}")
            print(f"먼저 다른 터미널창에서 `python3 sensor_simulator.py`가 구동중인지 확인하세요.")
            return

        try:
            while True:
                # 1바이트씩 네트워크 스트림에서 읽기
                data = sock.recv(1)
                if not data:
                    print(f"\n{RED}[경고] 서버와의 연결이 종료되었습니다.{RESET}")
                    break
                    
                byte_val = data[0]
                
                # 헤더 싱크 맞추기
                if len(self.buffer) == 0 and byte_val != 0x53:
                    continue
                if len(self.buffer) == 1 and byte_val != 0x59:
                    self.buffer.clear()
                    continue
                    
                self.buffer.append(byte_val)
                
                # 최소 패킷 길이 확보 (헤더(2)+제어(1)+명령(1)+길이(2)+체크섬(1)+엔드(2) = 최소 9바이트 + 데이터 1바이트 이상)
                if len(self.buffer) >= 10:
                    # 엔드바이트 (0x54 0x43) 확인
                    if self.buffer[-2] == 0x54 and self.buffer[-1] == 0x43:
                        # 체크섬 바이트는 엔드바이트 바로 앞
                        received_checksum = self.buffer[-3]
                        
                        # 체크섬 검증 대상 범위 (HEAD1부터 DATA의 끝까지)
                        pre_sum_array = self.buffer[:-3]
                        calculated_checksum = sum(pre_sum_array) & 0xFF
                        
                        if received_checksum == calculated_checksum:
                            # 올바른 패킷이므로 파싱
                            self.parse_frame(self.buffer)
                        else:
                            # 체크섬 불일치 오류 출력
                            print(f"\n{RED}[체크섬 오류] 계산값: 0x{calculated_checksum:02X}, 수신값: 0x{received_checksum:02X}{RESET}")
                        
                        # 다음 패킷을 위해 버퍼 비우기
                        self.buffer.clear()
                        
                # 버퍼 크기가 비정상적으로 길어지면 초기화하여 메모리 누수 방지
                if len(self.buffer) >= 64:
                    self.buffer.clear()
                    
        except KeyboardInterrupt:
            print(f"\n{RED}[수신기] 종료 요청이 감지되었습니다. 연결을 닫습니다.{RESET}")
        finally:
            sock.close()
            print(f"{GREEN}[수신기] 안전하게 종료되었습니다.{RESET}")

if __name__ == '__main__':
    # 윈도우 커맨드 창 등에서 한글 깨짐 방지 및 터미널 이스케이프 대응
    if sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        
    receiver = MR60BHA2Receiver()
    receiver.run()
