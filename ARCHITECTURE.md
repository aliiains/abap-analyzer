# ABAP Code Analyser — Архитектура

## Обзор

Приложение построено по принципам **SOLID** и разделено на пять независимых
модулей. Каждый модуль несёт единственную ответственность и взаимодействует
с другими только через чётко определённые интерфейсы (абстрактные классы).

```
main.py
  └── gui.py          ← точка сборки: создаёт App и запускает mainloop
        ├── parser.py ← лексический и структурный анализ ABAP
        ├── metrics.py← вычисление метрик по результату парсинга
        └── report.py ← формирование текстового отчёта
```

---

## Принципы проектирования

### S — Single Responsibility (единственная ответственность)
Каждый класс делает ровно одно:

| Класс | Ответственность |
|-------|-----------------|
| `ABAPLexer` | Разбивает строку на токены |
| `ABAPParser` | Строит структуру из токенов |
| `MetricsCalculator` | Считает метрики по `ParseResult` |
| `ReportGenerator` | Превращает метрики в читаемый текст |
| `SyntaxHighlighter` | Красит теги в виджете Tkinter |
| `HeatmapPainter` | Окрашивает фон строк по глубине вложенности |
| `App` | Связывает все компоненты, управляет событиями GUI |

### O — Open/Closed (открыт для расширения, закрыт для изменений)
Новые виды метрик добавляются через новый подкласс `BaseMetric`, без изменения
`MetricsCalculator`. Новый тип отчёта — через подкласс `BaseReportFormatter`.

### L — Liskov Substitution (принцип подстановки)
Все конкретные метрики наследуют `BaseMetric` и могут использоваться
взаимозаменяемо в `MetricsCalculator`.

### I — Interface Segregation (разделение интерфейсов)
`parser.py`, `metrics.py` и `report.py` не импортируют ничего из `gui.py`.
GUI знает об остальных модулях, но не наоборот.

### D — Dependency Inversion (инверсия зависимостей)
`MetricsCalculator` работает с абстракцией `ParseResult`, а не с конкретным
парсером. `ReportGenerator` принимает `MetricsReport`, независимо от того,
как он был получен.

---

## Модули

### `main.py`
Точка входа. Создаёт экземпляр `App` и вызывает `mainloop()`.
Не содержит бизнес-логики.

```
main.py
  └── App(root).run()
```

---

### `parser.py` — лексический и структурный анализ

#### Ключевые типы данных

```
Token
  ├── kind: str          ("KEYWORD", "STRING", "NUMBER", "COMMENT", "IDENT", ...)
  ├── value: str
  └── line: int

ABAPLine
  ├── lineno: int
  ├── raw: str
  ├── tokens: list[Token]
  ├── is_comment: bool
  ├── is_empty: bool
  └── depth: int          ← уровень вложенности этой строки

ParseResult
  ├── lines: list[ABAPLine]
  ├── errors: list[str]
  └── metadata: dict
```

#### Классы

| Класс | Роль |
|-------|------|
| `ABAPLexer` | Посимвольный разбор строки в список `Token` |
| `ABAPParser` | Перебирает строки, отслеживает вложенность через стек, формирует `ParseResult` |

#### Алгоритм отслеживания вложенности
`ABAPParser` поддерживает целочисленный счётчик `_depth`.
- Ключевые слова-открыватели (`IF`, `LOOP`, `DO`, `WHILE`, `SELECT`, `CASE`,
  `METHOD`, `FUNCTION`, `FORM`, `CLASS`, `TRY`, …) увеличивают счётчик
  **после** фиксации текущей глубины строки.
- Ключевые слова-закрыватели (`ENDIF`, `ENDLOOP`, `ENDDO`, …) уменьшают счётчик
  **до** фиксации.

---

### `metrics.py` — вычисление метрик

#### Иерархия классов

```
BaseMetric (ABC)
  ├── name: str          (абстрактное свойство)
  ├── compute(result) → MetricValue    (абстрактный метод)
  └── threshold() → MetricThreshold   (с умолчанием)

MetricValue
  ├── value: int | float
  └── level: str   ("ok", "warning", "error")

MetricsReport
  └── metrics: list[MetricValue]
```

#### Реализованные метрики

| Класс | Что считает |
|-------|-------------|
| `TotalLinesMetric` | Общее число строк |
| `CodeLinesMetric` | Строки с кодом (не пустые, не комментарии) |
| `CommentLinesMetric` | Строки-комментарии |
| `EmptyLinesMetric` | Пустые строки |
| `CyclomaticComplexityMetric` | Ветвления: IF, ELSEIF, CASE, WHEN, LOOP, DO, WHILE, CATCH |
| `MaxNestingDepthMetric` | Максимальный `depth` среди всех строк |
| `LongLinesMetric` | Строки длиннее 80 символов |
| `VeryLongLinesMetric` | Строки длиннее 120 символов |
| `MethodCountMetric` | Количество METHOD / FORM / FUNCTION |
| `AvgLineLengthMetric` | Средняя длина строк кода |

#### MetricsCalculator
Принимает список экземпляров `BaseMetric`, вызывает `compute()` на каждом,
собирает результаты в `MetricsReport`.
Набор метрик легко расширяется без правки самого `MetricsCalculator`.

---

### `report.py` — формирование отчёта

#### Иерархия классов

```
BaseReportFormatter (ABC)
  └── format(metrics_report, parse_result) → str

IssueDetector (ABC)
  └── detect(parse_result) → list[Issue]

Issue
  ├── line: int
  ├── level: str   ("ERROR", "WARNING", "INFO")
  ├── code: str    (напр. "W001")
  └── message: str

ReportGenerator
  ├── _formatters: list[BaseReportFormatter]
  └── _detectors: list[IssueDetector]
```

#### Детекторы замечаний

| Детектор | Что ищет |
|----------|----------|
| `LongLineDetector` | Строки > 80 символов |
| `VeryLongLineDetector` | Строки > 120 символов |
| `DeepNestingDetector` | Вложенность > 4 уровней |
| `EmptyCommentDetector` | Пустые строки комментариев |
| `MagicNumberDetector` | Числовые литералы вне объявлений |
| `TodoCommentDetector` | Комментарии с TODO / FIXME / HACK |
| `MissingEndifDetector` | Незакрытые IF-блоки |

#### Коды замечаний

| Код | Уровень | Описание |
|-----|---------|----------|
| E001 | ERROR | Незакрытый блок кода |
| W001 | WARNING | Строка длиннее 80 символов |
| W002 | WARNING | Строка длиннее 120 символов |
| W003 | WARNING | Глубокая вложенность (> 4 уровней) |
| W004 | WARNING | Магическое число в коде |
| I001 | INFO | TODO/FIXME в комментарии |
| I002 | INFO | Пустой комментарий |

---

### `gui.py` — графический интерфейс

#### Структура классов GUI

```
SyntaxHighlighter
  ├── highlight()   ← красит ключевые слова, строки, числа, комментарии
  └── clear()       ← снимает все теги

HeatmapPainter
  ├── paint(depths: list[int])         ← раскрашивает фон строк
  ├── clear()                          ← убирает все цвета фона
  └── depth_list_from_parse_result()   ← статический метод: ParseResult → list[int]

App
  ├── _build_window()     ← параметры главного окна
  ├── _build_menu()       ← строка меню
  ├── _build_toolbar()    ← панель кнопок
  ├── _build_panes()      ← левая и правая панели (PanedWindow)
  ├── _analyse()          ← главный обработчик «Анализировать»
  ├── _toggle_highlight() ← переключение подсветки
  ├── _toggle_heatmap()   ← переключение тепловой карты
  ├── _paste()            ← явный обработчик Ctrl+V
  ├── _open_file()        ← загрузка файла с диска
  └── _save_report()      ← сохранение отчёта на диск
```

#### Поток данных при нажатии «Анализировать»

```
Пользователь нажимает ▶ Анализировать
        │
        ▼
App._analyse()
        │
        ├─► ABAPParser.parse(source_code)
        │         └── возвращает ParseResult
        │
        ├─► MetricsCalculator.calculate(parse_result)
        │         └── возвращает MetricsReport
        │
        ├─► ReportGenerator.generate(metrics_report, parse_result)
        │         └── возвращает str (текст отчёта)
        │
        ├─► App._update_report_tab(report_text)
        │         └── показывает отчёт в правой панели
        │
        ├─► App._update_metrics_tab(metrics_report)
        │         └── заполняет таблицу метрик
        │
        └─► App._apply_heatmap(parse_result)  ← если тепловая карта ВКЛ
                  └── HeatmapPainter.paint(depths)
```

---

## Цветовая схема тепловой карты

| Уровень вложенности | Цвет HEX | Визуальное ощущение |
|---------------------|----------|---------------------|
| 0 | `#1e1e1e` (фон) | нейтральный тёмный |
| 1 | `#27201a` | едва тёплый |
| 2 | `#321e10` | янтарный |
| 3 | `#3e1a08` | коричнево-оранжевый |
| 4 | `#4d1205` | тёмно-оранжевый |
| 5 | `#5d0a04` | насыщенно-красный |
| 6 | `#6e0505` | малиновый |
| 7+ | `#7a0303` | тёмно-бордовый |

---

## Тестирование

Тесты расположены в папке `tests/` и покрывают все три бизнес-слоя:

| Файл | Что тестирует | Тестов |
|------|---------------|--------|
| `test_parser.py` | Лексер, парсер, вложенность, граничные случаи | ~60 |
| `test_metrics.py` | Каждую метрику в изоляции + `MetricsCalculator` | ~60 |
| `test_report.py` | Каждый детектор, форматтер, `ReportGenerator` | ~49 |

GUI (`gui.py`) не покрывается автотестами намеренно: Tkinter требует дисплея,
а логика GUI минимальна — она только связывает уже протестированные компоненты.

Запуск:
```bash
pytest tests/ -v
# или с покрытием:
pytest tests/ --cov=. --cov-report=term-missing
```

---

## Структура файлов

```
abap-analyzer/
├── main.py              ← точка входа (59 строк)
├── parser.py            ← лексер + парсер ABAP (~472 строки)
├── metrics.py           ← метрики (~690 строк)
├── report.py            ← отчёт + детекторы (~464 строки)
├── gui.py               ← интерфейс Tkinter (~1150 строк)
├── requirements.txt     ← только pytest и pytest-cov
├── build_exe.bat        ← сборка .exe на Windows (PyInstaller)
├── build_exe_mac.sh     ← сборка .app на macOS (PyInstaller)
├── README.md            ← руководство пользователя
├── ARCHITECTURE.md      ← этот файл
└── tests/
    ├── __init__.py
    ├── test_parser.py
    ├── test_metrics.py
    └── test_report.py
```

---

## Зависимости

### Runtime
Только стандартная библиотека Python:
- `tkinter` — GUI
- `re` — регулярные выражения
- `abc` — абстрактные классы
- `dataclasses` — структуры данных
- `typing` — аннотации типов
- `os`, `pathlib` — работа с файловой системой

### Dev / Test
- `pytest >= 7.4` — фреймворк тестирования
- `pytest-cov >= 4.1` — отчёт о покрытии

Сторонних runtime-зависимостей нет. Приложение запускается на чистом Python 3.10+.
