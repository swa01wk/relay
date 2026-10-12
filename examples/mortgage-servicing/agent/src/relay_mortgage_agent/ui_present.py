"""Build PRESENT_UI / SHOW_TABLE payloads for the Web SDK playground."""

from __future__ import annotations

from typing import Any


def _label(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").strip().title()


def table_surface(
    *,
    title: str,
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    caption: str | None = None,
    surface_id: str | None = None,
) -> dict[str, Any]:
    keys = columns or _column_keys(rows)
    return {
        "kind": "table",
        "id": surface_id,
        "title": title,
        "caption": caption,
        "columns": [{"key": key, "label": _label(key)} for key in keys],
        "rows": [{key: row.get(key) for key in keys} for row in rows],
    }


def kv_surface(
    *,
    title: str,
    items: dict[str, Any],
    surface_id: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "kv",
        "id": surface_id,
        "title": title,
        "items": [{"label": _label(key), "value": _cell(value)} for key, value in items.items()],
    }


def cards_surface(
    *,
    title: str,
    cards: list[dict[str, Any]],
    surface_id: str | None = None,
) -> dict[str, Any]:
    return {"kind": "cards", "id": surface_id, "title": title, "cards": cards}


def notice_surface(*, body: str, title: str | None = None) -> dict[str, Any]:
    return {"kind": "notice", "title": title, "body": body}


def present_ui_params(*surfaces: dict[str, Any], replace: bool = True) -> dict[str, Any]:
    return {"replace": replace, "surfaces": [s for s in surfaces if s]}


def _column_keys(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key in seen:
                continue
            seen.add(key)
            keys.append(str(key))
    return keys


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}" if value != int(value) else str(int(value))
    return str(value)


def customers_table(customers: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for customer in customers:
        mortgages = customer.get("mortgages") or []
        ids = ", ".join(str(m.get("id")) for m in mortgages if m.get("id"))
        rows.append(
            {
                "id": customer.get("id"),
                "name": customer.get("name"),
                "email": customer.get("email"),
                "mortgages": ids,
            }
        )
    return table_surface(title="Search results", rows=rows, surface_id="search-results")


def payments_table(mortgage_id: str, payments: list[dict[str, Any]]) -> dict[str, Any]:
    return table_surface(
        title=f"Payments — {mortgage_id}",
        rows=payments,
        columns=["month", "amount", "status", "paid_on"],
        surface_id="payments",
    )


def rates_table(mortgage_id: str, rates: list[dict[str, Any]]) -> dict[str, Any]:
    return table_surface(
        title=f"Rate history — {mortgage_id}",
        rows=rates,
        columns=["effective_date", "rate", "reason"],
        surface_id="rate-history",
    )


def case_kv(case: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "customer_name", "property", "status", "current_rate", "emi")
    items = {key: case.get(key) for key in keep if case.get(key) is not None}
    return kv_surface(title=f"Case {case.get('id') or ''}".strip(), items=items, surface_id="case")


def chart_surface(
    *,
    title: str,
    chart_type: str,
    x_key: str,
    series: list[str],
    data: list[dict[str, Any]],
    y_label: str | None = None,
    surface_id: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "chart",
        "id": surface_id,
        "title": title,
        "chart_type": chart_type,
        "x_key": x_key,
        "series": [{"key": key, "label": _label(key)} for key in series],
        "data": [{key: row.get(key) for key in (x_key, *series)} for row in data],
        "y_label": y_label,
    }


def rates_chart(mortgage_id: str, rates: list[dict[str, Any]]) -> dict[str, Any]:
    return chart_surface(
        title=f"Rate trend — {mortgage_id}",
        chart_type="line",
        x_key="effective_date",
        series=["rate"],
        data=rates,
        y_label="%",
        surface_id="rate-trend",
    )


def payments_chart(mortgage_id: str, payments: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(payments, key=lambda row: str(row.get("month")))
    return chart_surface(
        title=f"Payments — {mortgage_id}",
        chart_type="bar",
        x_key="month",
        series=["amount"],
        data=ordered,
        y_label="USD",
        surface_id="payments-chart",
    )
