#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MR60BHA2 mmWave 레이더 센서 가상 시뮬레이터 (sensor_simulator.py)

이 프로그램은 실제 MR60BHA2 센서의 UART 바이너리 프로토콜 규격에 맞게
가상 생체 데이터를 생성하여 시리얼 포트(PTY) 또는 TCP 소켓으로 송출하는 시뮬레이터입니다.

[사용방법]
1. 이 스크립트를 실행하면 가상 PTY 포트(/dev/pts/X 등) 및 TCP 서버(Port: 8888)가 열립니다.
2. CLI 화면에서 방향키나 단축키를 눌러 가상 인물의 호흡수, 심박수, 존재 여부 등을 실시간 조절할 수 있습니다.
"""

import os
import sys
import time
import socket
import random
import threading

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

class MR60BHA2Simulator:
    def __init__(self, port=8888):
        self.tcp_port = port
        self.running = True
        
        # 가상 생체 신호 상태값
        self.presence = 1      # 0: 없음, 1: 있음
        self.motion_state = 1  # 0: 정지, 1: 미세 움직임, 2: 활발함
        self.heart_rate = 72   # 심박수 (bpm)
        self.breath_rate = 16  # 호흡수 (rpm)
        self.distance = 1.25   # 타겟과의 거리 (meters)
        self.amplitude = 12    # 움직임 세기 (0-100)
        
        # 클라이언트 목록
        self.sockets = []
        self.pty_master = None
        self.pty_slave_name = None
        
        # PTY (가상 시리얼 포트) 생성 (Linux/macOS 지원)
        try:
            self.pty_master, slave = os.openpty()
            self.pty_slave_name = os.ttyname(slave)
        except Exception as e:
            self.pty_slave_name = "지원안됨 (OS 권한 또는 호환성 문제)"

    def build_packet(self, ctrl, cmd, data_bytes):
        """MR60BHA2 UART 표준 프로토콜 패킷 생성"""
        header = [0x53, 0x59]  # 'S', 'Y'
        footer = [0x54, 0x43]  # 'T', 'C'
        
        len_msb = (len(data_bytes) >> 8) & 0xFF
        len_lsb = len(data_bytes) & 0xFF
        
        # 헤더 + 제어 + 명령 + 데이터길이 + 데이터
        packet = header + [ctrl, cmd, len_msb, len_lsb] + data_bytes
        
        # 체크섬 계산 (바이트 합의 하위 8비트)
        checksum = sum(packet) & 0xFF
        packet.append(checksum)
        
        # 테일 추가
        packet += footer
        return bytes(packet)

    def send_to_all(self, packet):
        """모든 연결된 채널(TCP, PTY)에 바이너리 데이터 송신"""
        # 1. TCP 소켓 전송
        for sock in list(self.sockets):
            try:
                sock.sendall(packet)
            except Exception:
                self.sockets.remove(sock)
                
        # 2. Virtual Serial Port (PTY) 전송
        if self.pty_master:
            try:
                os.write(self.pty_master, packet)
            except Exception:
                pass

    def generator_loop(self):
        """실제 주기에 맞춰 무작위 노이즈가 섞인 센서 데이터 패킷 생성 전송"""
        print(f"{GREEN}[시뮬레이터] 데이터 송출 루프가 가동되었습니다.{RESET}")
        
        tick = 0
        while self.running:
            time.sleep(0.5)
            tick += 1
            
            # 가상 데이터에 자연스러운 노이즈 추가
            if self.presence == 1:
                # 심박수 미세 변동 (60 ~ 100 범위 보호)
                hr_delta = random.choice([-1, 0, 1])
                self.heart_rate = max(55, min(110, self.heart_rate + hr_delta))
                
                # 호흡수 미세 변동 (12 ~ 25 범위 보호)
                br_delta = random.choice([-1, 0, 0, 1]) if tick % 3 == 0 else 0
                self.breath_rate = max(10, min(28, self.breath_rate + br_delta))
                
                # 거리 변동 (정지 상태 시 초미세 진동)
                self.distance = max(0.4, min(3.5, self.distance + random.uniform(-0.01, 0.01)))
            else:
                self.heart_rate = 0
                self.breath_rate = 0
                self.distance = 0.0

            # 프로토콜 전송 주기 조율 (실제 레이더도 주기적으로 번갈아가며 보냄)
            
            # 1. 존재 유무 전송 (매 1.5초)
            if tick % 3 == 0:
                pkt = self.build_packet(0x80, 0x01, [self.presence])
                self.send_to_all(pkt)
                
            # 2. 움직임 상태 및 세기 전송 (매 2.0초)
            if tick % 4 == 1:
                m_state = self.motion_state if self.presence == 1 else 0
                amp = self.amplitude if self.presence == 1 else 0
                pkt_state = self.build_packet(0x80, 0x02, [m_state])
                pkt_amp = self.build_packet(0x80, 0x03, [amp])
                self.send_to_all(pkt_state)
                self.send_to_all(pkt_amp)
                
            # 3. 호흡수 전송 (매 2.5초)
            if tick % 5 == 2:
                pkt = self.build_packet(0x81, 0x01, [self.breath_rate])
                self.send_to_all(pkt)
                
            # 4. 심박수 전송 (매 3.0초)
            if tick % 6 == 3:
                pkt = self.build_packet(0x85, 0x02, [self.heart_rate])
                self.send_to_all(pkt)
                
            # 5. 거리 전송 (매 3.5초)
            if tick % 7 == 4:
                dist_cm = int(self.distance * 100)
                data_bytes = [(dist_cm >> 8) & 0xFF, dist_cm & 0xFF]
                pkt = self.build_packet(0x80, 0x04, data_bytes)
                self.send_to_all(pkt)

    def start_tcp_server(self):
        """외부 파이썬 리시버가 TCP로 연결할 수 있도록 서버 개방"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(('127.0.0.1', self.tcp_port))
            server.listen(5)
            server.settimeout(1.0)
        except Exception as e:
            print(f"{RED}[오류] TCP 포트 {self.tcp_port} 결합 실패: {e}{RESET}")
            return

        print(f"{GREEN}[TCP 서버] 127.0.0.1:{self.tcp_port} 에서 수신 대기 중...{RESET}")
        
        while self.running:
            try:
                conn, addr = server.accept()
                self.sockets.append(conn)
                print(f"\n{YELLOW}[연결 알림] 수신 클라이언트가 TCP 소켓으로 접속했습니다. ({addr[0]}:{addr[1]}){RESET}")
            except socket.timeout:
                continue
            except Exception:
                break
        server.close()

    def print_ui(self):
        """터미널에 가상 센서 상태 및 조작 UI 출력"""
        # 화면 청소
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{BOLD}{CYAN}====================================================={RESET}")
        print(f"{BOLD}{CYAN}      MR60BHA2 mmWave 센서 가상 하드웨어 시뮬레이터     {RESET}")
        print(f"{BOLD}{CYAN}====================================================={RESET}")
        print(f" * 가상 시리얼 포트 (PTY): {BOLD}{YELLOW}{self.pty_slave_name}{RESET}")
        print(f" * 가상 TCP 스트리밍 서버: {BOLD}{YELLOW}127.0.0.1:{self.tcp_port}{RESET}")
        print(f" * 활성 연결 대수: {BOLD}{GREEN}{len(self.sockets)} 대{RESET}")
        print(f"-----------------------------------------------------")
        print(f" [가상 피실험자 실시간 생체 수치]")
        
        presence_str = f"{GREEN}인체 감지됨 (Someone Here){RESET}" if self.presence == 1 else f"{RED}비어 있음 (No One){RESET}"
        print(f"  - 존재 상태  : {presence_str}")
        
        motion_map = {0: "움직임 없음 (None)", 1: "정지/미세진동 (Static)", 2: "활발한 움직임 (Active)"}
        print(f"  - 움직임 상태: {self.motion_state} - {motion_map.get(self.motion_state)}")
        print(f"  - 움직임 강도: {self.amplitude} / 100")
        print(f"  - 가상 심박수: {BOLD}{RED}{self.heart_rate} bpm{RESET}")
        print(f"  - 가상 호흡수: {BOLD}{BLUE}{self.breath_rate} rpm{RESET}")
        print(f"  - 대상 거리  : {self.distance:.2f} m")
        print(f"-----------------------------------------------------")
        print(f" [실시간 값 수동 조작 단축키]")
        print(f"  {BOLD}P{RESET} : 존재 유무 토글 (현재: {self.presence})")
        print(f"  {BOLD}M{RESET} : 움직임 상태 전환 (0 &rarr; 1 &rarr; 2)")
        print(f"  {BOLD}[ / ]{RESET} : 심박수 감소 / 증가  (현재: {self.heart_rate})")
        print(f"  {BOLD}- / ={RESET} : 호흡수 감소 / 증가  (현재: {self.breath_rate})")
        print(f"  {BOLD}< / >{RESET} : 감지 거리 단축 / 연장 (현재: {self.distance:.2f}m)")
        print(f"  {BOLD}Q{RESET} : 시뮬레이터 프로그램 종료")
        print(f"{CYAN}====================================================={RESET}")
        print("명령 입력 >> ", end="")
        sys.stdout.flush()

    def keyboard_controller(self):
        """키보드 입력을 받아 가상 생체 수치를 실시간 조정"""
        import select
        
        while self.running:
            self.print_ui()
            # 1초 타임아웃으로 입력을 대기
            rlist, _, _ = select.select([sys.stdin], [], [], 1.0)
            if rlist:
                char = sys.stdin.readline().strip().upper()
                if not char:
                    continue
                
                if char == 'Q':
                    self.running = False
                    print(f"\n{RED}[시뮬레이터] 시스템을 종료하는 중...{RESET}")
                    break
                elif char == 'P':
                    self.presence = 1 - self.presence
                elif char == 'M':
                    self.motion_state = (self.motion_state + 1) % 3
                elif char == '[':
                    self.heart_rate = max(40, self.heart_rate - 5)
                elif char == ']':
                    self.heart_rate = min(160, self.heart_rate + 5)
                elif char == '-':
                    self.breath_rate = max(6, self.breath_rate - 2)
                elif char == '=':
                    self.breath_rate = min(40, self.breath_rate + 2)
                elif char == '<':
                    self.distance = max(0.4, self.distance - 0.1)
                elif char == '>':
                    self.distance = min(6.0, self.distance + 0.1)

    def run(self):
        # 데이터 송출 스레드 시작
        gen_thread = threading.Thread(target=self.generator_loop, daemon=True)
        gen_thread.start()
        
        # TCP 소켓 서버 스레드 시작
        tcp_thread = threading.Thread(target=self.start_tcp_server, daemon=True)
        tcp_thread.start()
        
        # 메인 루프에서 키보드 컨트롤러 구동
        try:
            self.keyboard_controller()
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.cleanup()

    def cleanup(self):
        self.running = False
        for sock in self.sockets:
            try:
                sock.close()
            except Exception:
                pass
        if self.pty_master:
            try:
                os.close(self.pty_master)
            except Exception:
                pass
        print(f"{GREEN}[시뮬레이터] 정상 종료 완료.{RESET}")

if __name__ == '__main__':
    sim = MR60BHA2Simulator()
    sim.run()
