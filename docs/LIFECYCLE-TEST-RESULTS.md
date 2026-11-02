# Проверка упрощённого PR1

Дата: 2026-11-02. Ветка `feature/xray-balancer-minimal` от `main` (`0aa3793`).
Архитектура и границы гарантий: [LIFECYCLE.md](LIFECYCLE.md).

## Linux: среда и результаты предыдущего полного прогона

Linux-хост; готовый локальный Docker-образ `os-xray-test:php84` на Alpine 3.23.0,
PHP CLI 8.4.27, Python 3.12.16. Контейнеры без внешней сети; репозиторий подключён
только для чтения. Все изменяемые test fixtures — временные файлы контейнера.
Тестовое ядро для CLI Validate — исполняемый Python fixture, не Xray-core.

- PHP syntax: все 14 `.php` внутри plugin и `xray.inc` — PASS.
- Shell syntax: install.sh, upgrade.sh, 50-xray — PASS.
- `static_compat_test.py` — PASS, включая закреплённые версии и API-контракт.
- `behavioral_actions_test.py` — 50 сценариев production lifecycle (32 прежних + 18 регрессий review) плюс
  10 сценариев настоящего CLI switch: PASS.
- `behavioral_stop_test.py` — PASS.
- `behavioral_lock_test.py` — PASS: реальный flock/exec, отсутствие наследования.
- `behavioral_socks_test.py` — PASS.
- `behavioral_config_test.py` — PASS: legacy JSON/YAML, flat/vnext/generic outbound,
  defaults, invalid JSON и замороженный digest дорефакторинговой конфигурации.
- `behavioral_candidate_test.py` — PASS: настоящий PHP CLI, SimpleXML, builder,
  запуск внешнего валидатора, его отказ, отсутствие ядра, UUID/configd placeholder,
  приватные права и удаление временного кандидата.
- `upgrade_publication_test.py` — PASS: для каждого из install.sh/upgrade.sh
  прерывание перед каждой из 7 публикаций плюс успешная публикация (16 сценариев).
  Исполняется извлечённый production shell-блок в временных каталогах, не установщик.
- `behavioral_validate_api_test.py` — PASS: saved UUID metadata, точный backend
  command, invalid UUID/GET без вызова configd, legacy API без UUID.
- `gui_validate_test.js` — PASS (Node 22.22.1): 4 проверки production JS с DOM/AJAX
  adapters: выбран второй экземпляр, новый несохранённый, поздний ответ, invalid ID;
  также syntax всего шаблона после подстановки переводов.
- `behavioral_process_identity_test.py` — PASS: production PID/Stop helpers,
  неопределённая identity без сигналов, чужой PID, подтверждённая остановка,
  ошибка scan и подтверждённое отсутствие процессов.
- `git diff --check` — PASS; Python AST файлов tests — PASS.

## P0

| Сценарий | Доказательство | Результат Linux |
| --- | --- | --- |
| Первый Start | Production prepare/stop/files/launch/coordinator; ОС адаптирована | PASS |
| Stop | Оба компонента остановлены, flag установлен, hash снят | PASS |
| Повторный Start | Flag снят, оба компонента запущены | PASS |
| Restart | Реальная ветка coordinator вызывает остановку и новый запуск | PASS |
| Изменённый Apply | Новые JSON/YAML установлены, hash соответствует новой конфигурации | PASS |
| Неизменённый Apply | Ни остановок, ни запусков, ни network reload | PASS |
| Validate корректный | Actual CLI → XML → builder → внешний fixture | PASS |
| Validate некорректный | Отказ core fixture / malformed JSON; runtime не затронут | PASS |
| Несколько экземпляров | Независимые Start и Apply | PASS |
| Запуск после reboot | 7 последовательных входов boot после имитации потери процессов/hash | PASS, reboot имитируется |
| Watchdog: один компонент упал | По очереди отсутствуют Xray и tun2socks | PASS |
| Watchdog: административный Stop | Нет попыток запуска | PASS |

## P1

| Сценарий | Результат Linux |
| --- | --- |
| Последний кандидат в общем Apply невалиден: никто не остановлен | PASS |
| Общие Start/Restart/Apply: конфликты SOCKS/TUN до остановки | PASS |
| Конфликт с прежним runtime при изменённом XML | PASS |
| Конфликт SOCKS с удалённым из XML живым экземпляром | PASS |
| Ошибка запуска Xray и tun2socks, включая первый Start | PASS |
| Отказ второго Stop: первый уже применён и работает; второй восстанавливает недостающий компонент | PASS |
| Partial Start при отсутствии одного из компонентов | PASS |
| Failed A не блокирует успешный Apply независимого B | PASS |
| Failed A не блокирует 7 повторных watchdog-восстановлений B | PASS |
| Повторный Start после неполной первой записи JSON/YAML | PASS |
| Отказ backup write: работающий экземпляр не остановлен | PASS |
| Отказ записи/rename при установке и rollback: backup сохранён, повторная попытка успешна | PASS |
| Сохранение SOCKS/TUN/MTU legacy после failed Apply | PASS |
| Старый runtime без hash: no-op Apply и обычное изменение настроек | PASS |
| Семантически эквивалентный YAML не блокирует изменение legacy | PASS |
| Передача TUN/SOCKS от отключённого к включённому профилю | PASS |
| Short write и fallback tempnam в иной каталог: рабочий файл сохранён | PASS |
| Private backup 0600; при failed rollback нет ложного hash/Stop | PASS |
| Отказ записи административного flag: процессы не остановлены | PASS |
| Общий Stop охватывает удалённые из XML экземпляры | PASS |
| Частичный Apply/rollback возвращает ошибку, но инициирует reload | PASS |
| Прерывание публикации PHP зависимостей/controller main → PR1 | PASS, изолированный shell-блок |

P0/P1 lifecycle-тесты выполняют **настоящие функции** подготовки, файловых операций,
backup, Stop, launch, coordinator и CLI dispatch. Подменяются внешние операции
ОС: запуск/сигналы процессов, чтение NativeTun, команды назначения интерфейса и core test.
Парсер OPNsense assignment `xray_network` выполняется из production-кода с SimpleXML,
включая первый запуск без назначения. Watchdog/coordinator также не подменяются.
Файловые записи, rename и повторное чтение backup выполняются реально.
Нельзя трактовать эти PASS как запуск VPN на FreeBSD.

## Регрессии последнего review

Все перечисленные проверки — PASS на Linux, с теми же границами адаптеров:

- Первый Start без assignment: процессы работают, warning присутствует, hash
  отсутствует; после добавления assignment Apply завершает сеть без restart.
- Невалидный существующий assignment: preflight отказывает без остановки.
- Изменённый TUN в XML без Apply: watchdog не меняет runtime.
- Неудачный новый TUN, успешный rollback и три следующих watchdog: старая пара
  сохраняется, повторного Apply нет.
- Падение по очереди Xray/tun2socks при сохранённых новых SOCKS/TUN/outbound:
  восстанавливается старый runtime, survivor не получает stop.
- Отсутствующий hash и несогласованный YAML proxy: диагностируемый отказ recovery.
- Boot при утрате /var/run hash → падение компонента → watchdog старого runtime.
- Stop с отсутствующим YAML, повреждённым JSON, частичной парой; ошибка Stop
  сохраняет административный флаг, watchdog не запускает экземпляр.
- Reload: реальный CLI dispatch для Stop, повторного Stop, частичной остановки,
  отключения последнего экземпляра, rollback failure и удаления последнего UUID.
- Delete → Apply передаёт освобождённый ресурс, при invalid candidate не останавливает
  удалённый UUID; отказ Stop не блокирует независимый профиль. UUID найден также
  по одному оставшемуся YAML, когда JSON утрачен.
- CLI Validate fixture запускается через `sys.executable` текущего теста;
  FreeBSD workflow использует `python3.11`, наличия команды `python3` не требуется.

## Дополнительная проверка предыдущего Critical

Трассировка сохранённого PHP-кода показала `new → quiesce → cancel(new)`.
Настоящий архивный C-launcher собран во временном каталоге хоста; вызовы
`cancel <new-token>` и `start <new-token> /bin/true` дали 0 и 3 соответственно.
Это отдельная проверка старого дефекта на Linux. C-launcher отсутствует в новом PR1
и не требуется ни новым runtime, ни его тестам.

## Реальные интеграционные испытания: OPNsense 26.7.8_2

Дата: **2 ноября 2026 года**. Источник — результаты испытаний, предоставленные
пользователем; Codex не подключался к VM и не повторял эти действия. Это отдельные
лабораторные испытания, а не результаты запуска GitHub FreeBSD CI.

Среда: OPNsense 26.7.8_2 amd64, FreeBSD в изолированной VM Proxmox, Xray-core
26.3.27, реальный tun2socks с NativeTun. Установленный os-xray 3.1.3 обновлён
файлами PR1 через `upgrade.sh`. Отдельный Linux-клиент использовал OPNsense как
маршрутизатор; реальный VLESS-трафик направлялся через TUN посредством policy
routing. Лаборатория изолирована от production. Точная версия FreeBSD и вывод
версии tun2socks отдельно в предоставленном протоколе не зафиксированы.

### Процессы, файлы и управление на FreeBSD

| Сценарий | Подтверждённый результат |
| --- | --- |
| Обновление работающего os-xray 3.1.3 через upgrade.sh | PASS: PID обоих компонентов и config.xml сохранились, перезапуска не было |
| Validate сохранённого экземпляра | PASS: проверка настоящим Xray-core 26.3.27 |
| Отдельный no-op Apply | PASS: PID не изменились |
| Apply изменённого loglevel | PASS: ожидаемый перезапуск, работоспособность маршрута сохранилась |
| Административный Stop | PASS: процессов нет; ручной вызов watchdog их не запускает |
| Start после Stop | PASS: оба компонента запущены |
| Принудительное завершение дочернего tun2socks | PASS: watchdog восстановил tun2socks, работающий Xray сохранился |
| Настоящий reboot OPNsense | PASS: Xray, tun2socks, NativeTun и маршрут восстановились без ручного Apply |
| Общий Apply с невалидным кандидатом | PASS: Xray отклонил кандидат до остановки рабочего экземпляра, его PID сохранились |
| Удаление временного невалидного экземпляра → Apply | PASS: операция успешна, PID рабочего экземпляра сохранились |
| Реальный отказ запуска кандидата → rollback | PASS: ошибка Apply возвращена, прежние файлы восстановлены, прежняя конфигурация запущена заново, backup сохранён |

Невалидный кандидат находился в отдельном временном enabled-экземпляре с уникальными
SOCKS/TUN и синтаксически корректным JSON. Настоящий Xray отверг протокол
`nonexistent-pr1-test` с сообщением `unknown config id: nonexistent-pr1-test`.
Первая попытка испытания содержала дублирующийся TUN: контроллер правильно отклонил
конфликт до остановки. После исправления тестовых данных проверка повторена.
Это подтверждение проверки ресурсов, а не дефект PR1.

Для проверки rollback предварительно создан снапшот VM. Временный `nc` занял
другой loopback SOCKS-порт; этот порт сохранили в настройках рабочего экземпляра.
Штатный `xray run -test` принял конфигурацию, но новый процесс Xray не смог
запуститься из-за занятого порта. Контроллер вернул ошибку применения и восстановил
старый runtime. Обезличенный результат:

```text
Stopped.
ERROR: Install/start failed for <instance-uuid>
Already stopped.
Started <instance-uuid>.
WARNING: Previous runtime restored; Apply failed.
Backup retained: <backup-path>
ERROR: One or more Xray operations failed
```

«Прежний runtime восстановлен» означает повторный запуск прежней конфигурации,
а не сохранение старых PID. После испытания исходный SOCKS-порт вернули в сохранённые
настройки, `nc` остановили, завершающий Apply прошёл без ошибок. **Отдельная сверка
PID для этого последнего Apply не выполнялась**; отсутствие его перезапуска
не заявляется. Успешный rollback доказан реальными процессами FreeBSD, а не только
Linux-адаптерами. Отказ самого rollback этим испытанием не покрыт.

### Реальный packet path

Пользователь подтвердил передачу клиентского трафика через policy routing → TUN →
VLESS после обновления, изменённого Apply, восстановления tun2socks, reboot и
rollback. При отклонении невалидного кандидата трафик продолжал проходить.
После возврата сохранённых настроек и завершающего Apply VPN работал.

Это подтверждение сквозного клиентского маршрута перечисленных сценариев.
Оно не означает проверку всех TCP/UDP/IPv6 режимов, производительности или
сохранения уже установленных соединений при restart/rollback. Секреты, реальные
outbound, адреса и UUID лаборатории в отчёт не включены.

## GUI-01 и ограниченная проверка после интеграции

Селекторы `logInstanceSelect` и `diagInstanceSelect` расположены в `input-group-sm`. В опубликованном
[CSS темы OPNsense](https://github.com/opnsense/core/blob/master/src/opnsense/www/themes/opnsense/build/css/main.css)
для такого select высота и line-height равны 31px при вертикальном padding 5px.
При отключённом нативном appearance это даёт несогласованные размеры строки и
доступной области текста; такая комбинация объясняет смещение названия вниз.
CSS лабораторного браузера непосредственно не снимался: это диагноз по исходникам,
а не отдельное измерение computed style на VM.

Оба селектора используют общий локальный класс `xray-instance-selector` в
`general.volt`, ограниченный контейнером `#xray-instance-tabs`: `line-height: normal`,
сохранённые классы/высота/цвета темы, ограниченная ширина группы, фиксированная раскладка таблицы,
перенос toolbar и ellipsis для длинного выбранного имени с отступом под стрелку.
Глобальные CSS-правила не добавлялись. ID, options, UUID и обработчики выбора не
изменены. Полный текст имени сохраняется в option; сокращается только отображение.

Ограниченная проверка предыдущей правки Log и документации:

- `gui_validate_test.js`: PASS, 4 прежние проверки и syntax production JavaScript.
- `gui_logs_test.js`: PASS, локальность оформления и ограничения ширины (static),
  длинное синтетическое Unicode-имя как текст, сохранение выбранного UUID,
  удалённый выбор, fallback имени на UUID и пустой список (DOM/AJAX adapters).
- `static_compat_test.py`, `behavioral_validate_api_test.py`: PASS.
- PHP syntax: 14 PHP-файлов и `xray.inc`: PASS.
- `git diff --check`: PASS.
- Lifecycle, installer и boot/watchdog runtime не менялись. Предыдущая большая
  аварийная матрица повторно не запускалась; её результаты выше относятся к
  предыдущему прогону. Новых зависимостей не установлено.

### Дополнение: общий стиль Log и Diagnostics

По сообщению пользователя **Log визуально проверен на лабораторной OPNsense
26.7.8_2: отображение корректно**. На Diagnostics подтверждён такой же прежний
дефект. Исправление распространено на Diagnostics; уже проверенные значения
оформления Log перенесены из inline-атрибутов в общий локальный класс без изменения
значений. Для Diagnostics добавлена такая же доступная подпись поля.

Проверка шаблонов, форм и JavaScript Xray обнаружила только эти два селектора
экземпляров. Dropdown уровня логирования в форме экземпляра не является выбором
экземпляра и не менялся. UUID, options, обработчики и production JavaScript не
менялись; lifecycle, API и генератор также не затронуты.

Проверки этого дополнения:

- `gui_logs_test.js`: PASS, оба шаблона подключают общий класс, все CSS-селекторы
  ограничены контейнером Xray; сохранены line-height, ограничения ширины и ellipsis.
  DOM/AJAX-проверки охватывают оба поля: длинное Unicode-имя, независимый выбор UUID,
  обновление списка, удалённый выбор, fallback на UUID и пустой список.
- `gui_validate_test.js`: PASS, прежние 4 сценария и syntax production JavaScript.
- `node --check tests/gui_logs_test.js`, `static_compat_test.py`, `git diff --check`: PASS.
- Контрольные суммы API, моделей, генератора, lifecycle и `scripts.volt` не изменились.

### Итоговая визуальная приёмка C2

Пользователь подтвердил: **оба селектора, Diagnostics и Log, визуально проверены
на лабораторной OPNsense 26.7.8_2 после установки последнего исправления общего
CSS-класса**. Это результат реальной визуальной проверки пользователя; локальные
DOM/syntax-тесты не выдаются за её доказательство. GUI в правках B1/C1 не менялся.

## Финальные правки B1/C1 и целевые регрессии

### B1: недостоверный applied hash после watchdog recovery

Причина: старое подтверждение сохранялось при восстановлении компонента и оставалось
на диске после ошибки настройки сети. Здоровая пара с теми же файлами затем могла
пройти Start/Apply как no-op, хотя настройка сети не была подтверждена.

Теперь recovery читает прежний hash, затем удаляет его **до** попытки восстановления.
Отказ удаления возвращает явную ошибку и запрещает recovery. Успешный запуск с
успешной настройкой сети создаёт подтверждение заново. При сетевой ошибке процессы
могут продолжить работать без hash; status показывает `unconfirmed`. Следующий
явный Start/Apply повторяет сетевую настройку без перезапуска неизменённой пары.
Если удаление невозможно, старый файл физически остаётся; операция завершается
ошибкой до изменений, а не маскирует её успешным recovery.

Команда ограниченного прогона: `python3 tests/behavioral_actions_test.py --review-fixes`.
Результат: **13 lifecycle-сценариев + 3 CLI-сценария — PASS**.

- `B1_network_failure_then_apply`: работающий экземпляр с hash → потеря tun2socks →
  recovery → успешная первая команда ifconfig и отказ второй (`inet`) → оба процесса
  работают, hash отсутствует, `network_state=unconfirmed` → здоровая пара не
  перезапускается watchdog → снятие отказа → явный Apply повторяет настройку без
  restart → hash восстановлен, `network_state=applied`.
- `B1_invalidation_failure`: ошибка unlink hash даёт диагностируемый отказ без
  запуска/остановки/сетевых изменений; после снятия отказа recovery успешен.
- Прежние целевые регрессии: healthy no-op Apply, Stop/Start, административный Stop
  и watchdog, потеря компонентов, saved TUN без Apply, компонент при отличающемся
  XML, watchdog после rollback, успешный rollback при отказах Xray/tun2socks,
  неподтверждённый runtime, boot → watchdog.
- CLI: unchanged Apply без reload, частичный Apply/rollback с reload и Stop.

В этих тестах выполняются production recovery/launch/status/Apply и теперь также
`xray_setup_network`; ошибка инъецируется на границе `exec` для сетевой команды.
Это **Linux behavioral fault injection**, а не доказательство воспроизведения
конкретного отказа ifconfig на FreeBSD. Прежний реальный успешный rollback из
лабораторного протокола остаётся отдельным результатом.

### C1: актуальный Boot log

Существующий Boot log API продолжает читать `/tmp/xray_syshook.log`. Источник записи
восстановлен в общем входе `boot` контроллера, используемом syshook и plugin hook;
сам syshook не изменён. При отказе operation lock команда boot также пишет failed
до выхода с кодом 1. Запись не захватывает operation lock; при конкуренции видна
последняя целиком опубликованная запись. Пишется UTC-время и короткий результат последнего вызова:
started/completed/failed. Каждая запись заменяет предыдущую через существующий
atomic writer (0600), поэтому рост ограничен и полный вывод/секреты не сохраняются.
Ошибка записи даёт WARNING без подмены результата boot. Watchdog и reload-only
сохраняют прежнюю семантику и не обновляют Boot log.

`behavioral_boot_log_test.py`: **6 групп проверок — PASS**:

- Реальный shell syshook с перенаправленными путями → production PHP dispatch и
  atomic writer: success/failure дают свежую однострочную запись менее 200 байт,
  заменяют старую; синтетический секрет из вывода lifecycle не попадает в файл.
- Watchdog и `--reload-only` оставляют запись без изменений.
- При реальном занятом flock повторный boot возвращает код 1 и заменяет прежний
  completed на failed; другие команды журнал не меняют. После освобождения lock
  штатный boot успешен.
- Два конкурирующих PHP-контроллера публикуют целые записи без deadlock: отказ
  второго boot не прерывает владельца lock, который затем успешно завершает работу.
- Штатная команда tail из actions_xray.conf → production API `logAction` через
  configd-адаптер возвращает текущую запись; сохранён контракт GUI Boot log.
- Отказ публикации на symlink даёт WARNING, не меняет файл-цель и код успешного boot.

Реальные сервисные операции внутри этого теста адаптированы. Это локальная проверка
цепочки записи/чтения, не новый boot лабораторной OPNsense и не browser-тест.

Дополнительно: PHP syntax (14 PHP-файлов и xray.inc), shell syntax существующего
syshook, syntax изменённых Python-тестов, static compatibility и `git diff --check`
— PASS. Полная аварийная матрица не повторялась. Новые состояния, сервисы и зависимости
не добавлялись; модель, config.xml, версии ядер, GUI и builder не менялись.

Ограничение B1: после успешной инвалидации и неудачного recovery автоматическая
повторная попытка для неподтверждённого runtime требует явного Start/Apply.
Boot log хранит только последний результат; при ошибке его записи может остаться
старая запись, сопровождаемая WARNING. Принятые ограничения минимального lifecycle
ниже сохраняются без новых обещаний отказоустойчивости.

## Ещё не подтверждено на целевой системе

- Первоначальный запуск непосредственно PR1 с неназначенным TUN и завершение
  назначения через GUI без restart.
- Несколько одновременно активных экземпляров и передача ресурсов между ними.
  Временный невалидный enabled-экземпляр не доказывает многопроцессный сценарий.
- Восстановление после неудачного rollback, ошибок записи/rename или нехватки места.
- Все варианты install/upgrade/uninstall; проверен только описанный успешный upgrade.
- Отказ Stop, повреждённые runtime-файлы и неопределённая identity на целевой ОС.
- Падение Xray отдельно от tun2socks; выполнение watchdog по cron, а не ручным вызовом.
- Сохранённый новый TUN без Apply; повторные watchdog после rollback при всё ещё
  отличающихся сохранённых параметрах; GUI Validate второго экземпляра и draft.
- Остановка удалённого **работающего** UUID через общий Apply: временный удалённый
  экземпляр в испытании не был запущен.
- Исчерпывающая проверка PF/interface reload, reentry и timeout configd.

Осознанно принятые ограничения минимального lifecycle сохраняются:

- поздний запуск процесса после timeout не исключён полностью;
- произвольный power-cut между файловыми операциями не покрыт транзакционным восстановлением;
- окно PID reuse полностью не устранено;
- rollback не является общей транзакцией PF, интерфейсов и нескольких экземпляров;
- весь комплект файлов обновления не публикуется одной атомарной операцией.

FreeBSD CI содержит переносимые тесты и интеграционные packet-path проверки.
Его запуск в этой сессии не выполнялся; лабораторные PASS не подменяют результат CI.

## Оценка

Минимальный PR1 готов к финальному code review: основные штатные операции,
сохранение трафика при отклонении кандидата и реальный успешный rollback подтверждены
на OPNsense 26.7.8_2. Оба селектора визуально приняты пользователем после последней
правки. B1/C1 проверены целевыми локальными регрессиями и готовы к короткому
повторному review только исправленных участков. Полная production-сертификация
всех сценариев не заявляется. Новый архитектурный цикл не требуется.

## Файлы для review

- `.github/workflows/compat-check.yml`
- `.github/workflows/freebsd-runtime.yml`
- `docs/LIFECYCLE-TEST-RESULTS.md` — новый
- `docs/LIFECYCLE.md` — новый
- `install.sh`
- `plugin/etc/inc/plugins.inc.d/xray.inc`
- `plugin/etc/rc.syshook.d/start/50-xray`
- `plugin/mvc/app/controllers/OPNsense/Xray/Api/InstanceController.php`
- `plugin/mvc/app/controllers/OPNsense/Xray/Api/ServiceController.php`
- `plugin/mvc/app/views/OPNsense/Xray/partials/scripts.volt`
- `plugin/mvc/app/views/OPNsense/Xray/partials/tab_logs.volt`
- `plugin/mvc/app/views/OPNsense/Xray/partials/tab_diagnostics.volt`
- `plugin/mvc/app/views/OPNsense/Xray/general.volt`
- `plugin/scripts/Xray/xray-apply.php` — новый
- `plugin/scripts/Xray/xray-config.php` — новый
- `plugin/scripts/Xray/xray-service-control.php`
- `plugin/scripts/Xray/xray-watchdog.php`
- `tests/behavioral_actions_test.py`
- `tests/behavioral_candidate_test.py` — новый
- `tests/behavioral_config_test.py` — новый
- `tests/behavioral_lock_test.py`
- `tests/behavioral_stop_test.py`
- `tests/freebsd_xray_core_integration.py`
- `tests/static_compat_test.py`
- `tests/upgrade_publication_test.py` — новый
- `tests/behavioral_validate_api_test.py` — новый
- `tests/behavioral_process_identity_test.py` — новый
- `tests/behavioral_boot_log_test.py` — новый
- `tests/gui_validate_test.js` — новый
- `tests/gui_logs_test.js` — новый
- `upgrade.sh`

Рекомендуемый порядок review: builder и legacy fixtures → prepare/preflight →
apply_one/rollback → CLI Stop/launch → boot/watchdog/reload → публикация обновления.
Особое внимание: first Start, changed Apply, partial-stop repair, retained backup,
реальная семантика daemon/PID/TUN на целевой системе.

Перечень выше включает новые файлы PR1. При подготовке локального коммита они
включаются явно; полнота состава проверяется через staged diff, включая документацию
и тесты. Архивный эксперимент остаётся в отдельной локальной ветке.
