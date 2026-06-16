# ABAP Code Analyser — Тестирование

## Быстрый старт

```bash
cd abap-analyzer

# Установка зависимостей (один раз)
python -m pip install pytest pytest-cov

# Запустить все тесты
python -m pytest tests/ -v

# Запустить с отчётом о покрытии
python -m pytest tests/ --cov=. --cov-report=term-missing
```

Ожидаемый результат: **169 passed**

---

## Структура тестов

```
tests/
├── __init__.py
├── test_parser.py    — 496 строк, ~60 тестов
├── test_metrics.py   — 513 строк, ~60 тестов
└── test_report.py    — 490 строк, ~49 тестов
```

---

## Что покрывают тесты

### `test_parser.py` — парсер и лексер

#### ABAPLexer
| Тест | Что проверяется |
|------|-----------------|
| `test_tokenize_keyword` | Ключевое слово распознаётся как токен `KEYWORD` |
| `test_tokenize_string` | Строка в одинарных кавычках — токен `STRING` |
| `test_tokenize_number` | Целые и дробные числа — токен `NUMBER` |
| `test_tokenize_comment_star` | Строка с `*` в начале — токен `COMMENT` |
| `test_tokenize_comment_quote` | Строка с `"` в начале — токен `COMMENT` |
| `test_tokenize_mixed_line` | Строка с ключевым словом, числом и строкой |
| `test_tokenize_empty_line` | Пустая строка возвращает пустой список токенов |
| `test_tokenize_identifier` | Имена переменных — токен `IDENT` |
| `test_case_insensitive` | `if`, `IF`, `If` распознаются одинаково |

#### ABAPParser — базовый разбор
| Тест | Что проверяется |
|------|-----------------|
| `test_parse_empty_string` | Пустой ввод → пустой `ParseResult` без ошибок |
| `test_parse_single_line` | Одна строка кода — одна запись в `lines` |
| `test_parse_comment_line` | Строка комментария помечается `is_comment=True` |
| `test_parse_empty_line` | Пустая строка помечается `is_empty=True` |
| `test_parse_multiline` | Несколько строк разбираются корректно |
| `test_parse_preserves_raw` | Исходный текст строки сохраняется в `raw` |
| `test_parse_line_numbers` | Номера строк начинаются с 1, идут по порядку |

#### ABAPParser — вложенность
| Тест | Что проверяется |
|------|-----------------|
| `test_depth_flat_code` | Код без блоков — глубина везде 0 |
| `test_depth_if_endif` | `IF` увеличивает глубину, `ENDIF` уменьшает |
| `test_depth_loop_endloop` | `LOOP` / `ENDLOOP` отслеживается корректно |
| `test_depth_nested_if` | Вложенные `IF` внутри `IF` — глубина 2 |
| `test_depth_nested_loop_if` | `LOOP` + `IF` внутри — корректная вложенность |
| `test_depth_case_when` | `CASE / WHEN / ENDCASE` — глубина учитывается |
| `test_depth_do_enddo` | `DO / ENDDO` |
| `test_depth_while_endwhile` | `WHILE / ENDWHILE` |
| `test_depth_try_catch` | `TRY / CATCH / ENDTRY` |
| `test_depth_form_endform` | `FORM / ENDFORM` — подпрограмма |
| `test_depth_method_endmethod` | `METHOD / ENDMETHOD` |
| `test_depth_function_endfunction` | `FUNCTION / ENDFUNCTION` |
| `test_depth_select_endselect` | `SELECT / ENDSELECT` |
| `test_depth_deeply_nested` | Вложенность 4+ уровней |
| `test_depth_unclosed_block` | Незакрытый блок не вызывает исключение |
| `test_depth_extra_end` | Лишний `ENDIF` не уходит в отрицательные значения |

#### Граничные случаи
| Тест | Что проверяется |
|------|-----------------|
| `test_parse_only_comments` | Файл только из комментариев |
| `test_parse_only_empty_lines` | Файл только из пустых строк |
| `test_parse_windows_line_endings` | Строки с `\r\n` разбираются корректно |
| `test_parse_very_long_line` | Строка 500+ символов не вызывает ошибку |
| `test_parse_unicode_in_string` | Не-ASCII символы в строковых литералах |
| `test_parse_keywords_in_strings` | Ключевые слова внутри строк не считаются блоками |

---

### `test_metrics.py` — метрики

#### Тесты каждой метрики в изоляции
| Метрика | Что тестируется |
|---------|-----------------|
| `TotalLinesMetric` | Пустой ввод = 0; N строк = N; только комментарии |
| `CodeLinesMetric` | Считает только не-пустые, не-комментарий строки |
| `CommentLinesMetric` | `*` и `"` в начале строки; встроенные комментарии не считаются |
| `EmptyLinesMetric` | Пустые строки; строки с пробелами |
| `CyclomaticComplexityMetric` | Базовая сложность 1; каждый `IF` +1; `CASE/WHEN` +1 каждый; `LOOP`, `DO`, `WHILE`, `CATCH` +1 |
| `MaxNestingDepthMetric` | Плоский код = 0; корректный максимум при вложенности |
| `LongLinesMetric` | Строки ровно 80 символов не считаются; 81+ считаются |
| `VeryLongLinesMetric` | Порог 120 символов |
| `MethodCountMetric` | `METHOD`, `FORM`, `FUNCTION` — каждое +1 |
| `AvgLineLengthMetric` | Корректное среднее; только строки кода |

#### Пороговые значения (уровни WARNING / ERROR)
| Тест | Что проверяется |
|------|-----------------|
| `test_complexity_ok_level` | Сложность ≤ 10 → уровень `ok` |
| `test_complexity_warning_level` | Сложность 11–20 → `warning` |
| `test_complexity_error_level` | Сложность > 20 → `error` |
| `test_nesting_ok_level` | Глубина ≤ 4 → `ok` |
| `test_nesting_warning_level` | Глубина 5–6 → `warning` |
| `test_nesting_error_level` | Глубина ≥ 7 → `error` |
| `test_long_lines_ok` | 0 длинных строк → `ok` |
| `test_long_lines_warning` | 1–10 длинных строк → `warning` |
| `test_long_lines_error` | > 10 длинных строк → `error` |

#### MetricsCalculator
| Тест | Что проверяется |
|------|-----------------|
| `test_calculator_returns_report` | Возвращает `MetricsReport` |
| `test_calculator_all_metrics_present` | Все 10 метрик присутствуют в отчёте |
| `test_calculator_empty_input` | Пустой ввод — все метрики = 0, без исключений |
| `test_calculator_custom_metric_list` | Передача подмножества метрик работает корректно |

---

### `test_report.py` — отчёт и детекторы

#### Детекторы замечаний
| Детектор | Тестируется |
|----------|-------------|
| `LongLineDetector` | Строка 80 символов — нет замечания; 81 — есть |
| `VeryLongLineDetector` | Порог 120 символов |
| `DeepNestingDetector` | Глубина ≤ 4 — нет; ≥ 5 — замечание с номером строки |
| `EmptyCommentDetector` | `*` и `"` без текста после → `I002` |
| `MagicNumberDetector` | Числа вне объявлений → `W004`; `CONSTANTS` / `DATA` исключены |
| `TodoCommentDetector` | `TODO`, `FIXME`, `HACK` (любой регистр) → `I001` |
| `MissingEndifDetector` | Незакрытый `IF` → `E001`; закрытый — нет замечания |

#### ReportGenerator
| Тест | Что проверяется |
|------|-----------------|
| `test_report_contains_metrics` | Отчёт включает блок метрик |
| `test_report_contains_issues` | Замечания выводятся с кодом и номером строки |
| `test_report_empty_input` | Пустой ввод — отчёт без исключений |
| `test_report_issue_levels` | ERROR / WARNING / INFO присутствуют в нужных местах |
| `test_report_is_string` | Результат всегда строка |
| `test_report_no_issues` | Чистый код → раздел замечаний пуст или содержит «нет замечаний» |

---

## Уровень покрытия

| Модуль | Покрытие | Примечание |
|--------|----------|------------|
| `parser.py` | ~95% | Все ветви парсера и лексера |
| `metrics.py` | ~97% | Все метрики и пороговые значения |
| `report.py` | ~94% | Все детекторы и форматтер |
| `gui.py` | 0% | Намеренно — требует дисплей (Tkinter) |
| `main.py` | 0% | Намеренно — точка входа |
| **Итого (без GUI)** | **~95%** | |

> GUI не тестируется автоматически: Tkinter требует запущенного дисплея,
> а логика GUI минимальна — она только связывает уже протестированные компоненты.

---

## Запуск отдельных наборов тестов

```bash
# Только парсер
python -m pytest tests/test_parser.py -v

# Только метрики
python -m pytest tests/test_metrics.py -v

# Только отчёт
python -m pytest tests/test_report.py -v

# Один конкретный тест
python -m pytest tests/test_metrics.py::TestCyclomaticComplexity::test_complexity_warning_level -v

# Тесты по ключевому слову
python -m pytest tests/ -k "nesting" -v

# С отчётом покрытия в HTML
python -m pytest tests/ --cov=. --cov-report=html
# Открыть: htmlcov/index.html
```

---

## Добавление нового теста

1. Определите модуль: `test_parser.py`, `test_metrics.py` или `test_report.py`
2. Добавьте метод в соответствующий класс `Test*`
3. Имя начинается с `test_`, описывает сценарий: `test_complexity_with_nested_loops`
4. Используйте реальные объекты (`ABAPParser`, `MetricsCalculator`), не моки
5. Проверьте что тест падает до фикса и проходит после

```python
# Пример нового теста для метрики
def test_new_metric_boundary(self):
    source = "IF x > 0.\nENDIF."
    result = ABAPParser().parse(source)
    report = MetricsCalculator().calculate(result)
    value = next(m for m in report.metrics if m.name == "Cyclomatic Complexity")
    assert value.value == 2
```
