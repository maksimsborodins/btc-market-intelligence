# Спецификация схем данных, контрактов и артефактов (Schemas & Contracts)

---

## 1. Контракты ключевых интерфейсных функций ядра

### 1.1. `calculate_atr_risk_levels`
Вычисляет параметры динамической риск-модели на основе текущей спотовой цены, волатильности ATR14 и значения Quant Bias.

```python
def calculate_atr_risk_levels(
    spot_price: float,
    atr14: float,
    quant_bias_score: int
) -> dict:
```

**Возвращаемая структура:**
```json
{
  "atr14": 1103.78,
  "buffer": 1655.67,
  "direction": "SHORT",
  "entry_price": 82272.29,
  "long": {
    "stop_loss": 80616.62,
    "tp1_rr2": 85583.63,
    "tp2_rr3": 87239.30,
    "risk_usd": 1655.67,
    "risk_pct": 2.01
  },
  "short": {
    "stop_loss": 83927.96,
    "tp1_rr2": 78960.95,
    "tp2_rr3": 77305.28,
    "risk_usd": 1655.67,
    "risk_pct": 2.01
  },
  "recommended": {
    "scenario": "SHORT",
    "stop_loss": 83927.96,
    "tp1_rr2": 78960.95,
    "tp2_rr3": 77305.28
  }
}
```

---

### 1.2. `fetch_onchain_metrics`
Опрашивает BGeometrics REST API для определения макроэкономической фазы Bitcoin.

```python
def fetch_onchain_metrics(session: Optional[requests.Session] = None) -> dict:
```

**Возвращаемая структура:**
```json
{
  "mvrv_zscore": 0.96,
  "mvrv_stage": "Fair Value / Early Bull",
  "nupl": 0.353,
  "nupl_stage": "Optimism / Anxiety",
  "realized_price": 53437.54,
  "status": "OK"
}
```

---

### 1.3. `run_fast_momentum_scan`
Точка входа для быстрого параллельного REST-сканирования рынка.

```python
def run_fast_momentum_scan(quiet: bool = False) -> dict:
```

**Возвращает:** Полный словарь снимка рынка (`snapshot`), который сохраняется в `market_snapshot.json`.

---

## 2. Схемы персистентных JSON артефактов

### 2.1. `market_snapshot.json` (Текущий срез рынка)
Атомарный файл состояния, генерируемый при каждом быстром или полном сканировании.

```json
{
  "timestamp_utc": "2026-10-16T10:43:10+00:00",
  "execution_time_sec": 1.04,
  "spot_price": 82272.29,
  "futures_price": 82237.20,
  "basis_usd": -35.09,
  "basis_pct": -0.04,
  "quant_bias": {
    "score": -22,
    "label": "BEARISH",
    "factors": {
      "vwap_trend_1d": -15,
      "cvd_spot_24h": -20,
      "orderbook_imbalance_spot": 10,
      "orderbook_imbalance_futures": -13,
      "divergence_engine_24h": 15
    }
  },
  "derivatives": {
    "open_interest_btc": 94073.6,
    "open_interest_zscore": 0.82,
    "funding_rate": 0.000041,
    "funding_zscore": 0.49
  },
  "atr_risk": {
    "atr14": 1103.78,
    "buffer": 1655.67,
    "direction": "SHORT",
    "recommended": {
      "scenario": "SHORT",
      "stop_loss": 83927.96,
      "tp1_rr2": 78960.95,
      "tp2_rr3": 77305.28
    }
  },
  "onchain": {
    "mvrv_zscore": 0.96,
    "mvrv_stage": "Fair Value / Early Bull",
    "nupl": 0.353,
    "nupl_stage": "Optimism / Anxiety",
    "realized_price": 53437.54,
    "status": "OK"
  }
}
```

---

### 2.2. `quant_calibration_tracker.json` (Калибровка винрейта)
Файл накопления сигналов и математической оценки эффективности модели.

```json
{
  "summary": {
    "total_signals": 10,
    "evaluated_signals": 5,
    "wins": 2,
    "losses": 3,
    "winrate_pct": 40.0
  },
  "history": [
    {
      "signal_id": "SIG_20261015_090000",
      "timestamp": "2026-10-15T09:00:00+00:00",
      "scenario": "SHORT",
      "entry_price": 83450.0,
      "stop_loss": 84950.0,
      "tp1_rr2": 80450.0,
      "tp2_rr3": 78950.0,
      "quant_bias": -35,
      "status": "WIN",
      "exit_price": 80400.0,
      "pnl_pct": 3.65
    }
  ]
}
```

---

### 2.3. `daemon_status.json` (Пульс автономного демона)
```json
{
  "status": "RUNNING",
  "pid": 4812,
  "started_at": 1792147390.12,
  "last_iteration_at": "2026-10-16T10:43:10+00:00",
  "iteration_count": 142,
  "last_execution_sec": 1.04,
  "last_error": null
}
```

---

## 3. Схема аналитического отчета (`daily_report.md` / `daily_report.pdf`)

Сводный отчет компилируется при запуске полного цикла анализа и включает в себя:
1. **Резюме руководителя (Executive Summary):** Текущая рыночная фаза, сводный скоринг Quant Bias, направление и рекомендуемый риск.
2. **Квантовая декомпозиция факторов:** Таблица весов индикаторов, анализ кумулятивной дельты объемов (CVD) и книги ордеров.
3. **Деривативный блок:** Анализ открытого интереса (OI Z-Score), ставки бессрочного финансирования (Funding Rate) и расчет базиса спот/фьючерс.
4. **Таблица уровней риска (Dynamic ATR Risk Plan):** Четкие ценовые координаты для входа, фиксации прибыли и защитного закрытия.
5. **Ончейн-метрики и тепловые карты:** Графики ликвидаций, фаза MVRV/NUPL.
