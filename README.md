# os-xray

[![Release](https://img.shields.io/github/v/release/MrTheory/os-xray)](https://github.com/MrTheory/os-xray/releases)
[![License](https://img.shields.io/github/license/MrTheory/os-xray)](https://github.com/MrTheory/os-xray/blob/main/LICENSE)
[![Downloads](https://img.shields.io/github/downloads/MrTheory/os-xray/total)](https://github.com/MrTheory/os-xray/releases)
[![OPNsense](https://img.shields.io/badge/OPNsense-25.x%20%2F%2026.x-blue)](https://opnsense.org)
[![FreeBSD](https://img.shields.io/badge/FreeBSD-14.x%20amd64-red)](https://freebsd.org)

**Xray-core (VLESS+Reality) VPN plugin for OPNsense**

Xray-core с протоколом VLESS+Reality + tun2socks — нативный VPN-клиент для OPNsense с поддержкой селективной маршрутизации. Обходит DPI-блокировки за счёт маскировки трафика под легитимный TLS.

---

## Возможности

- Импорт VLESS-ссылки одной кнопкой — **Import VLESS link → Parse & Fill**
- Полная поддержка параметров VLESS+Reality (UUID, flow, SNI, PublicKey, ShortID, Fingerprint)
- Управление туннелем через GUI: **VPN → Xray**
- При установке автоматически определяет и импортирует существующий конфиг xray-core и tun2socks
- Совместимость с селективной маршрутизацией OPNsense (Firewall Aliases + Rules + Gateway)
- Статус сервисов xray-core и tun2socks обновляется в GUI каждые 5 секунд
- **Кнопки Start / Stop / Restart** — управление сервисом прямо из GUI без перезагрузки страницы
- **Кнопка Validate Config** — сухой прогон конфига через `xray -test` без остановки сервиса
- **Кнопка Test Connection** — проверяет, что xray-core реально проксирует трафик
- **Вкладка Log** — Boot Log и Xray Core Log прямо в GUI
- **Вкладка Diagnostics** — статистика TUN-интерфейса: IP, MTU, байты, пакеты, uptime процессов
- **Watchdog** — автоматический перезапуск при падении xray-core или tun2socks (настраивается)
- **Автозапуск после ребута** — интерфейс поднимается автоматически, нажимать Apply вручную не нужно
- ACL-права — доступ к GUI и API только для авторизованных пользователей с ролью `page-vpn-xray`

---

## Стек

```
xray-core (VLESS+Reality)
    ↓ SOCKS5 127.0.0.1:10808
tun2socks
    ↓ TUN интерфейс proxytun2socks0
OPNsense Gateway PROXYTUN_GW
    ↓
Firewall Rules (селективная маршрутизация)
```

---

## Системные требования

| Компонент  | Версия                  |
|------------|-------------------------|
| OPNsense   | 25.x / 26.x             |
| FreeBSD    | 14.x amd64              |
| xray-core  | Любая актуальная        |
| tun2socks  | Любая актуальная        |

---

## Установка

```sh
fetch -o /tmp/os-xray-v5.tar https://raw.githubusercontent.com/MrTheory/os-xray/refs/heads/main/os-xray-v5.tar
cd /tmp && tar xf os-xray-v5.tar && cd os-xray-v5
sh install.sh
```

Установщик автоматически:

- Проверит наличие бинарников xray-core и tun2socks — если их нет, выведет ссылки для скачивания
- Проверит, не занят ли SOCKS5-порт (10808 по умолчанию) другим процессом
- Найдёт существующие конфиги и импортирует их в OPNsense (поля в GUI заполнятся сразу)
- Скопирует все файлы плагина, перезапустит configd, очистит кеши
- Установит boot-скрипт для автозапуска после ребута

---

## Настройка в GUI

Обнови браузер (`Ctrl+F5`) → **VPN → Xray**

1. Вкладка **Instance** → кнопка **Import VLESS link** → вставь ссылку → **Parse & Fill**
2. Вкладка **General** → установи галку **Enable Xray** (и **Enable Watchdog** по желанию)
3. Нажми **Apply**
4. Кнопка **Test Connection** — убедись, что туннель работает (показывает HTTP 200)
5. Кнопка **Validate Config** — проверить конфиг без перезапуска сервиса

---

## Интерфейс и шлюз

| Шаг | Путь в GUI | Значение |
|-----|-----------|----------|
| Назначить интерфейс | Interfaces → Assignments | + Add: proxytun2socks0 |
| Включить и настроить | Interfaces → \<имя\> | Enable ✓, IPv4: Static, IP: `10.255.0.1/30` |
| **Предотвратить удаление** | Interfaces → \<имя\> | **Prevent interface removal ✓** |
| Создать шлюз | System → Gateways → Add | Gateway IP: `10.255.0.2`, Far Gateway ✓, Monitoring off ✓ |

> **Важно:** галочка **Prevent interface removal** обязательна — без неё OPNsense может удалить интерфейс из конфига при ребуте, если tun2socks ещё не успел его создать.

---

## Селективная маршрутизация

- **Firewall → Aliases** — создай список IP/сетей/доменов для маршрутизации через VPN
- **Firewall → Rules → LAN** — добавь правило: Source = LAN net, Destination = alias, Gateway = PROXYTUN_GW

MSS Clamping для Xray не требуется (в отличие от WireGuard).

---

## Автозапуск после ребута

После ребута интерфейс `proxytun2socks0` поднимается автоматически — xray и tun2socks стартуют, интерфейс получает IP, firewall rules перезагружаются. Вручную нажимать Apply не нужно.

Работает через два механизма с защитой от двойного запуска (flock):
- **`xray_configure_do()`** — boot hook (приоритет 10), запускает процессы на раннем этапе загрузки
- **`/usr/local/etc/rc.syshook.d/start/50-xray`** — финальный скрипт, поднимает интерфейс и применяет routing/firewall когда OPNsense полностью загружен

Лог сохраняется в `/tmp/xray_syshook.log` (дозапись, ротация при превышении 50 KB).

---

## Watchdog

При включённом **Enable Watchdog** cron каждую минуту проверяет живость xray-core и tun2socks. При падении любого из процессов — оба перезапускаются автоматически. События пишутся в `/var/log/xray-watchdog.log` (ротация: 3 файла по 100 KB).

Watchdog не перезапускает сервис если он был остановлен вручную через кнопку **Stop** или **Apply** с отключённым Enable.

---

## Остановка сервиса

При остановке (`Stop` в GUI или `Apply` с отключённым Enable) плагин:
1. Останавливает tun2socks — он сам уничтожает TUN-интерфейс при завершении
2. Останавливает xray-core
3. Выставляет флаг намеренной остановки — watchdog не будет перезапускать сервис

---

## Удаление

```sh
cd /tmp/os-xray-v5
sh install.sh uninstall
```

---

## Устранение неполадок

### Меню VPN → Xray не появляется

```sh
rm -f /var/lib/php/tmp/opnsense_menu_cache.xml
# Затем Ctrl+F5 в браузере
```

### Проверить статус сервисов

```sh
/usr/local/opnsense/scripts/Xray/xray-service-control.php status
# {"status":"ok","xray_core":"running","tun2socks":"running"}
```

### Проверить соединение через туннель

```sh
curl --socks5 127.0.0.1:10808 -s -o /dev/null -w "%{http_code}" https://1.1.1.1 --max-time 5
# 200 = OK
```

### Просмотреть логи

```sh
# Boot-лог (автозапуск, назначение IP, reload firewall)
cat /tmp/xray_syshook.log

# Лог xray-core и tun2socks (ошибки подключения, Reality handshake)
tail -50 /var/log/xray-core.log

# Лог watchdog (перезапуски процессов)
tail -50 /var/log/xray-watchdog.log

# Ошибки PHP (проблемы с GUI или API)
tail -30 /var/lib/php/tmp/PHP_errors.log
```

### Проверить процессы и PID-файлы

```sh
# Запущены ли процессы
ps aux | grep -E 'xray|tun2socks'

# PID-файлы
cat /var/run/xray_core.pid
cat /var/run/tun2socks.pid

# Флаг намеренной остановки (если есть — watchdog не перезапустит)
cat /var/run/xray_stopped.flag
```

### Проверить TUN-интерфейс

```sh
ifconfig proxytun2socks0
# Должен быть UP и иметь inet адрес (например 10.255.0.1)

# Статистика трафика через интерфейс
netstat -ibn | grep proxytun2socks0
```

### Проверить конфиги

```sh
# Конфиг xray-core (генерируется при Apply)
cat /usr/local/etc/xray-core/config.json

# Конфиг tun2socks
cat /usr/local/tun2socks/config.yaml

# Сухой прогон конфига без перезапуска сервиса
/usr/local/opnsense/scripts/Xray/xray-service-control.php validate
```

### Проверить lock и race condition

```sh
# Не завис ли lock (если Start/Restart не реагирует)
ls -la /var/run/xray_start.lock
# Если файл старый — удалить вручную:
rm -f /var/run/xray_start.lock
```

### Ручной запуск и отладка

```sh
# Запустить вручную с выводом в консоль
/usr/local/opnsense/scripts/Xray/xray-service-control.php start

# Остановить вручную
/usr/local/opnsense/scripts/Xray/xray-service-control.php stop

# Перезапустить
/usr/local/opnsense/scripts/Xray/xray-service-control.php restart

# Запустить boot-скрипт вручную с выводом
sh /usr/local/etc/rc.syshook.d/start/50-xray

# Запустить watchdog вручную
/usr/local/opnsense/scripts/Xray/xray-watchdog.php
```

### Проверить configd

```sh
# Список зарегистрированных actions xray
grep -A3 '\[xray' /usr/local/opnsense/service/conf/actions.d/actions_xray.conf

# Перезапустить configd если actions не работают
service configd restart
```

### Сброс и переустановка

```sh
# Полная переустановка без потери конфига OPNsense
cd /tmp/os-xray-v5
sh install.sh uninstall
sh install.sh
```

---

## Структура файлов

```
os-xray/
├── install.sh
├── CHANGELOG.md
└── plugin/
    ├── +MANIFEST                               ← FreeBSD pkg метаданные
    ├── etc/
    │   ├── inc/plugins.inc.d/
    │   │   └── xray.inc                        ← регистрация сервиса, boot hook, cron watchdog
    │   ├── newsyslog.conf.d/
    │   │   └── xray.conf                       ← ротация xray-core.log и xray-watchdog.log
    │   └── rc.syshook.d/start/
    │       └── 50-xray                         ← автозапуск после ребута
    ├── scripts/Xray/
    │   ├── xray-service-control.php            ← управление xray-core и tun2socks
    │   ├── xray-watchdog.php                   ← watchdog: проверка и перезапуск процессов
    │   ├── xray-ifstats.php                    ← статистика TUN-интерфейса для Diagnostics
    │   └── xray-testconnect.php                ← проверка соединения через SOCKS5
    ├── service/conf/actions.d/
    │   └── actions_xray.conf                   ← configd actions
    └── mvc/app/
        ├── models/OPNsense/Xray/
        │   ├── General.xml / General.php       ← модель: enable, watchdog (v1.0.1)
        │   ├── Instance.xml / Instance.php     ← модель: параметры подключения (v1.0.2)
        │   ├── ACL/ACL.xml                     ← права доступа (page-vpn-xray)
        │   └── Menu/Menu.xml                   ← пункт меню VPN → Xray
        ├── controllers/OPNsense/Xray/
        │   ├── IndexController.php
        │   ├── forms/general.xml
        │   ├── forms/instance.xml
        │   └── Api/
        │       ├── GeneralController.php
        │       ├── InstanceController.php
        │       ├── ServiceController.php       ← start/stop/restart/status/log/validate/diagnostics
        │       └── ImportController.php        ← парсинг VLESS-ссылки
        └── views/OPNsense/Xray/
            └── general.volt
```

---

## Если бинарники ещё не установлены

Установщик сам сообщит об отсутствии бинарников. Ниже — команды для ручной установки.

**xray-core** — [github.com/XTLS/Xray-core/releases](https://github.com/XTLS/Xray-core/releases)
```sh
fetch -o /tmp/xray.zip https://github.com/XTLS/Xray-core/releases/latest/download/Xray-freebsd-64.zip
cd /tmp && unzip xray.zip xray
install -m 0755 /tmp/xray /usr/local/bin/xray-core
```

**tun2socks** — [github.com/xjasonlyu/tun2socks/releases](https://github.com/xjasonlyu/tun2socks/releases)
```sh
fetch -o /tmp/tun2socks.zip https://github.com/xjasonlyu/tun2socks/releases/latest/download/tun2socks-freebsd-amd64.zip
cd /tmp && unzip tun2socks.zip
mkdir -p /usr/local/tun2socks
install -m 0755 /tmp/tun2socks-freebsd-amd64 /usr/local/tun2socks/tun2socks
```

> Имя файла tun2socks после распаковки может отличаться в зависимости от версии — проверь командой `ls /tmp/tun2socks*`.

---

## Changelog

Полная история изменений — в файле [CHANGELOG.md](CHANGELOG.md).

| Версия | Что изменилось |
|--------|---------------|
| 1.9.2  | Фикс fatal error tun2socks при stop, ротация watchdog лога |
| 1.9.1  | Хотфикс validate: синтаксис xray -test, расширение .json для tempnam |
| 1.9.0  | Улучшен hint для поля SOCKS5 Listen Address |
| 1.8.0  | Аудит безопасности: фиксы proc_kill, watchdog stopped flag, validate tempfile |
| 1.7.0  | Фикс блокировки GUI, фикс ifstats bytes, запуск 50-xray из do_start |
| 1.6.0  | BUG-5/9, Watchdog E1, Diagnostics E4, Validate Config E5 |
| 1.5.0  | Ротация лога, кнопки Start/Stop/Restart, вкладка Xray Core Log |
| 1.4.0  | Аудит безопасности P0-P2, xray-testconnect, flock, stderr в лог |
| 1.3.0  | Версионирование моделей, `+MANIFEST`, `Changelog.md` |
| 1.2.0  | Вкладка Log, кнопка Test Connection, интервал статуса 5 с |
| 1.1.0  | Надёжный install.sh: PHP-парсинг конфигов, check_port, ротация лога |
| 1.0.1  | Исправлен loglevel, TUN destroy при stop, flock |
| 1.0.0  | ACL, валидация UUID, санитизация ImportController |
| 0.9.0  | Первоначальный релиз |

---

## Лицензия

BSD 2-Clause License

Copyright (c) 2026 Merkulov Pavel Sergeevich (Меркулов Павел Сергеевич)

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.

---

## Автор

Меркулов Павел Сергеевич  
Февраль 2026

---

## Благодарности

- [XTLS/Xray-core](https://github.com/XTLS/Xray-core) — Xray-core и протокол VLESS+Reality
- [xjasonlyu/tun2socks](https://github.com/xjasonlyu/tun2socks) — tun2socks
- [OPNsense](https://opnsense.org) — открытая архитектура плагинов
- [yukh975](https://github.com/yukh975) - за помощь в тестировании
- [hohner36](https://github.com/hohner36) - за помощь в тестировании и настройке автоматизации
