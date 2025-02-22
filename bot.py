#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LayerEdge Auto-Ping BOT v1.0
Powered by <Ваш Watermark>
Описание: Бот для автоматического пинга, чек-ина и управления узлами LayerEdge с поддержкой прокси.
"""

import asyncio
import json
import os
import time
from datetime import datetime
import curses

import pytz
from aiohttp import ClientResponseError, ClientSession, ClientTimeout
from aiohttp_socks import ProxyConnector
from colorama import Fore, Style, init
from eth_account import Account
from eth_account.messages import encode_defunct
from fake_useragent import FakeUserAgent

# Инициализация colorama
init(autoreset=True)

# Временная зона (например, Asia/Jakarta)
WIB = pytz.timezone('Europe/Moscow')


def select_proxy_mode_menu(stdscr):
    """
    Интерактивное меню выбора режима работы с прокси.
    Используйте стрелки ↑/↓ для перемещения и Enter для выбора.
    """
    curses.curs_set(0)  # скрыть курсор
    stdscr.clear()
    options = ["Использовать Monosans Proxy", "Использовать приватные прокси", "Без прокси"]
    current_selection = 0

    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, "Выберите режим работы с прокси (↑/↓ и Enter):")
        for idx, option in enumerate(options):
            if idx == current_selection:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(idx + 2, 4, option)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(idx + 2, 4, option)
        key = stdscr.getch()
        if key == curses.KEY_UP and current_selection > 0:
            current_selection -= 1
        elif key == curses.KEY_DOWN and current_selection < len(options) - 1:
            current_selection += 1
        elif key in [10, 13]:
            return current_selection + 1  # возвращаем 1, 2 или 3


def select_proxy_mode():
    """Запуск интерактивного меню выбора режима прокси."""
    return curses.wrapper(select_proxy_mode_menu)


class LayerEdge:
    def __init__(self) -> None:
        """
        Инициализация бота:
         - Настройка заголовков для HTTP-запросов
         - Список прокси и параметры ротации
        """
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://dashboard.layeredge.io",
            "Referer": "https://dashboard.layeredge.io/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": FakeUserAgent().random
        }
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}

    def clear_terminal(self):
        """Очистка экрана терминала."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def welcome(self):
        """Отображение стильного баннера при запуске."""
        banner = f"""
 _   _           _  _____      
| \ | |         | ||____ |     
|  \| | ___   __| |    / /_ __ 
| . ` |/ _ \ / _` |    \ \ '__|
| |\  | (_) | (_| |.___/ / |   
\_| \_/\___/ \__,_|\____/|_|   
                               
LayerEdge Auto-Ping
    @nod3r
==============================================================================================
        """
        print(banner)

    def log(self, message):
        """
        Логирование сообщений с таймстампом.
        Формат: [HH:MM:SS] >> сообщение
        """
        timestamp = datetime.now().astimezone(WIB).strftime('%H:%M:%S')
        print(f"{Fore.LIGHTCYAN_EX}[{timestamp}]{Style.RESET_ALL} >> {message}")

    def format_seconds(self, seconds):
        """Преобразование секунд в формат ЧЧ:ММ:СС."""
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02}"

    def mask_account(self, account):
        """Маскировка приватного ключа для безопасности (отображаются лишь первые и последние 6 символов)."""
        return account[:6] + '*' * 6 + account[-6:]

    def print_message(self, address, proxy, color, message):
        """
        Вывод статуса в одной строке, без больших рамок:
         [HH:MM:SS] >> Account: ... | Proxy: ... | Status: ...
        """
        timestamp = datetime.now().astimezone(WIB).strftime('%H:%M:%S')
        print(
            f"{Fore.LIGHTCYAN_EX}[{timestamp}]{Style.RESET_ALL} >> "
            f"Account: {Fore.WHITE}{self.mask_account(address)}{Style.RESET_ALL} | "
            f"Proxy: {Fore.WHITE}{proxy}{Style.RESET_ALL} | "
            f"Status: {color}{message}{Style.RESET_ALL}"
        )

    async def print_clear_message(self):
        """
        Периодически выводит сообщение о завершении цикла.
        """
        while True:
            await asyncio.sleep(60)
            self.log(f"{Fore.BLUE}Все аккаунты обработаны успешно. Ожидание следующего цикла...{Style.RESET_ALL}")

    async def load_proxies(self, use_proxy_choice: int):
        """
        Загрузка списка прокси:
         - Если выбран режим Monosans Proxy (1), список загружается из GitHub.
         - Иначе используется локальный файл proxy.txt.
        """
        filename = "proxy.txt"
        try:
            if use_proxy_choice == 1:
                async with ClientSession(timeout=ClientTimeout(total=30)) as session:
                    async with session.get("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt") as response:
                        response.raise_for_status()
                        content = await response.text()
                        with open(filename, 'w') as f:
                            f.write(content)
                        self.proxies = content.splitlines()
            else:
                if not os.path.exists(filename):
                    self.log(f"{Fore.RED}Файл {filename} не найден.{Style.RESET_ALL}")
                    return
                with open(filename, 'r') as f:
                    self.proxies = f.read().splitlines()

            if not self.proxies:
                self.log(f"{Fore.RED}Прокси не найдены.{Style.RESET_ALL}")
                return

            self.log(f"{Fore.GREEN}Всего прокси: {len(self.proxies)}{Style.RESET_ALL}")

        except Exception as e:
            self.log(f"{Fore.RED}Ошибка загрузки прокси: {e}{Style.RESET_ALL}")
            self.proxies = []

    def check_proxy_schemes(self, proxy_str: str):
        """Проверка и корректировка схемы прокси."""
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        if any(proxy_str.startswith(s) for s in schemes):
            return proxy_str
        return f"http://{proxy_str}"

    def get_next_proxy_for_account(self, address):
        """
        Назначение следующего прокси для аккаунта.
        Если для аккаунта ещё не назначен прокси, выбирается текущий и индекс обновляется.
        """
        if address not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[address] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[address]

    def rotate_proxy_for_account(self, address):
        """Ротация прокси для аккаунта – выбирается следующий прокси из списка."""
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[address] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy

    def generate_address(self, account: str):
        """
        Генерация адреса кошелька из приватного ключа.
        Возвращается адрес или None при ошибке.
        """
        try:
            acct = Account.from_key(account)
            return acct.address
        except Exception:
            return None

    def generate_checkin_payload(self, account: str, address: str):
        """
        Формирование данных для ежедневного чек-ина.
        Подписывается сообщение и возвращаются необходимые параметры.
        """
        timestamp = int(time.time() * 1000)
        try:
            message = f"I am claiming my daily node point for {address} at {timestamp}"
            encoded = encode_defunct(text=message)
            signed = Account.sign_message(encoded, private_key=account)
            signature = signed.signature.hex()
            return {"sign": f"0x{signature}", "timestamp": timestamp, "walletAddress": address}
        except Exception:
            return None

    def generate_node_payload(self, account: str, address: str, msg_type: str):
        """
        Формирование данных для запроса активации/деактивации узла.
        """
        timestamp = int(time.time() * 1000)
        try:
            message = f"Node {msg_type} request for {address} at {timestamp}"
            encoded = encode_defunct(text=message)
            signed = Account.sign_message(encoded, private_key=account)
            signature = signed.signature.hex()
            return {"sign": f"0x{signature}", "timestamp": timestamp}
        except Exception:
            return None

    async def user_data(self, address: str, proxy=None, retries=5):
        """
        Получение информации о кошельке.
        При статусе 404 производится попытка регистрации.
        """
        url = f"https://referralapi.layeredge.io/api/referral/wallet-details/{address}"
        await asyncio.sleep(3)
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.get(url=url, headers=self.headers) as response:
                        if response.status == 404:
                            await self.user_confirm(address, proxy)
                            continue
                        response.raise_for_status()
                        result = await response.json()
                        return result.get('data')
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(self.mask_account(address), proxy, Fore.RED, f"Ошибка получения данных: {str(e)}")
                return None

    async def user_confirm(self, address: str, proxy=None, retries=5):
        """
        Регистрация кошелька, если он отсутствует.
        """
        url = "https://referralapi.layeredge.io/api/referral/register-wallet/tHc67a1g"
        data = json.dumps({"walletAddress": address})
        headers = {**self.headers, "Content-Length": str(len(data)), "Content-Type": "application/json"}
        await asyncio.sleep(3)
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(address, proxy, Fore.RED, f"Ошибка регистрации: {str(e)}")
                return None

    async def daily_checkin(self, account: str, address: str, proxy=None, retries=5):
        """
        Ежедневный чек-ин для получения очков.
        """
        url = "https://referralapi.layeredge.io/api/light-node/claim-node-points"
        payload = self.generate_checkin_payload(account, address)
        data = json.dumps(payload)
        headers = {**self.headers, "Content-Length": str(len(data)), "Content-Type": "application/json"}
        await asyncio.sleep(3)
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=120)) as session:
                    async with session.post(url=url, headers=headers, data=data) as response:
                        if response.status == 405:
                            self.print_message(address, proxy, Fore.YELLOW, "Чек-ин уже выполнен сегодня")
                            return None
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    payload = self.generate_checkin_payload(account, address)
                    data = json.dumps(payload)
                    continue
                self.print_message(address, proxy, Fore.RED, f"Ошибка чек-ина: {str(e)}")
                return None

    async def node_status(self, address: str, proxy=None, retries=5):
        """
        Получение статуса узла.
        """
        url = f"https://referralapi.layeredge.io/api/light-node/node-status/{address}"
        await asyncio.sleep(3)
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=120)) as session:
                    async with session.get(url=url, headers=self.headers) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(address, proxy, Fore.RED, f"Ошибка получения статуса узла: {str(e)}")
                return None

    async def start_node(self, account: str, address: str, proxy=None, retries=5):
        """
        Активация узла.
        """
        url = f"https://referralapi.layeredge.io/api/light-node/node-action/{address}/start"
        payload = self.generate_node_payload(account, address, "activation")
        data = json.dumps(payload)
        headers = {**self.headers, "Content-Length": str(len(data)), "Content-Type": "application/json"}
        await asyncio.sleep(3)
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=120)) as session:
                    async with session.post(url=url, headers=headers, data=data) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    payload = self.generate_node_payload(account, address, "activation")
                    data = json.dumps(payload)
                    continue
                self.print_message(address, proxy, Fore.RED, f"Ошибка запуска узла: {str(e)}")
                return None

    async def stop_node(self, account: str, address: str, proxy=None, retries=5):
        """
        Деактивация узла.
        """
        url = f"https://referralapi.layeredge.io/api/light-node/node-action/{address}/stop"
        payload = self.generate_node_payload(account, address, "deactivation")
        data = json.dumps(payload)
        headers = {**self.headers, "Content-Length": str(len(data)), "Content-Type": "application/json"}
        await asyncio.sleep(3)
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=120)) as session:
                    async with session.post(url=url, headers=headers, data=data) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    payload = self.generate_node_payload(account, address, "deactivation")
                    data = json.dumps(payload)
                    continue
                self.print_message(address, proxy, Fore.RED, f"Ошибка остановки узла: {str(e)}")
                return None

    async def process_user_earning(self, address: str, use_proxy: bool):
        """
        Периодическая проверка заработка узла.
        """
        while True:
            await asyncio.sleep(24 * 60 * 60)
            proxy = self.get_next_proxy_for_account(address) if use_proxy else None
            balance = "N/A"
            user = await self.user_data(address, proxy)
            if user:
                balance = user.get("nodePoints", "N/A")
            self.print_message(address, proxy, Fore.WHITE, f"Заработано {balance} очков")

    async def process_claim_checkin(self, account: str, address: str, use_proxy: bool):
        """
        Периодический чек-ин для получения очков.
        """
        while True:
            proxy = self.get_next_proxy_for_account(address) if use_proxy else None
            check_in = await self.daily_checkin(account, address, proxy)
            if check_in and check_in.get("message") == "node points claimed successfully":
                self.print_message(address, proxy, Fore.GREEN, "Чек-ин выполнен успешно")
            await asyncio.sleep(12 * 60 * 60)

    async def process_perform_node(self, account: str, address: str, use_proxy: bool):
        """
        Управление узлом: активация/деактивация по расписанию.
        """
        while True:
            proxy = self.get_next_proxy_for_account(address) if use_proxy else None
            reconnect_time = 10 * 60
            node = await self.node_status(address, proxy)
            if node and node.get("message") == "node status":
                last_connect = node['data'].get('startTimestamp')
                if last_connect is None:
                    start = await self.start_node(account, address, proxy)
                    if start and start.get("message") == "node action executed successfully":
                        last_connect = start['data'].get('startTimestamp')
                        now_time = int(time.time())
                        reconnect_time = last_connect + 86400 - now_time
                        self.print_message(
                            address,
                            proxy,
                            Fore.GREEN,
                            f"Узел подключен - Переподключение через: {self.format_seconds(reconnect_time)}"
                        )
                else:
                    now_time = int(time.time())
                    connect_time = last_connect + 86400
                    if now_time >= connect_time:
                        stop = await self.stop_node(account, address, proxy)
                        if stop and stop.get("message") == "node action executed successfully":
                            self.print_message(address, proxy, Fore.GREEN, "Узел отключен - Переподключение...")
                            await asyncio.sleep(3)
                            start = await self.start_node(account, address, proxy)
                            if start and start.get("message") == "node action executed successfully":
                                last_connect = start['data'].get('startTimestamp')
                                now_time = int(time.time())
                                reconnect_time = last_connect + 86400 - now_time
                                self.print_message(
                                    address,
                                    proxy,
                                    Fore.GREEN,
                                    f"Узел подключен - Переподключение через: {self.format_seconds(reconnect_time)}"
                                )
                    else:
                        reconnect_time = connect_time - now_time
                        self.print_message(
                            address,
                            proxy,
                            Fore.YELLOW,
                            f"Узел уже подключен - Переподключение через: {self.format_seconds(reconnect_time)}"
                        )
            await asyncio.sleep(reconnect_time)

    async def process_accounts(self, account: str, address: str, use_proxy: bool):
        """
        Обработка аккаунта:
         - Получение информации о кошельке
         - Запуск задач по мониторингу заработка, чек-ину и управлению узлом
        """
        proxy = self.get_next_proxy_for_account(address) if use_proxy else None
        user = None
        while user is None:
            user = await self.user_data(address, proxy)
            if not user:
                proxy = self.rotate_proxy_for_account(address) if use_proxy else None
                continue
            balance = user.get("nodePoints", "N/A")
            self.print_message(address, proxy, Fore.WHITE, f"Заработано {balance} очков")
            tasks = [
                self.process_user_earning(address, use_proxy),
                self.process_claim_checkin(account, address, use_proxy),
                self.process_perform_node(account, address, use_proxy)
            ]
            await asyncio.gather(*tasks)

    async def main(self):
        """
        Основная функция:
         - Чтение списка аккаунтов из файла
         - Выбор режима работы с прокси через интерактивное меню
         - Запуск задач для каждого аккаунта
        """
        try:
            with open('accounts.txt', 'r') as file:
                accounts = [line.strip() for line in file if line.strip()]

            # Выбор режима работы с прокси
            use_proxy_choice = select_proxy_mode()
            use_proxy = use_proxy_choice in [1, 2]

            # Очистка экрана и приветствие
            self.clear_terminal()
            self.welcome()

            # Лог: количество аккаунтов
            self.log(f"Всего аккаунтов: {len(accounts)}")

            # Загрузка прокси при необходимости
            if use_proxy:
                await self.load_proxies(use_proxy_choice)

            self.log("=" * 80)

            while True:
                tasks = []
                for account in accounts:
                    if account:
                        address = self.generate_address(account)
                        if not address:
                            self.log(
                                f"{Fore.RED}[Аккаунт: {self.mask_account(account)}] "
                                f"- Ошибка генерации адреса. Проверьте приватный ключ.{Style.RESET_ALL}"
                            )
                            continue
                        tasks.append(self.process_accounts(account, address, use_proxy))

                # Добавляем задачу на периодический вывод
                tasks.append(self.print_clear_message())

                await asyncio.gather(*tasks)
                await asyncio.sleep(10)

        except FileNotFoundError:
            self.log(f"{Fore.RED}Файл 'accounts.txt' не найден.{Style.RESET_ALL}")
            return
        except Exception as e:
            self.log(f"{Fore.RED}Ошибка: {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    try:
        bot = LayerEdge()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print(
            f"\n{Fore.LIGHTCYAN_EX}[{datetime.now().astimezone(WIB).strftime('%H:%M:%S')}] "
            f"{Fore.RED}[ ВЫХОД ] LayerEdge Auto-Ping BOT завершил работу.{Style.RESET_ALL}\n"
        )
