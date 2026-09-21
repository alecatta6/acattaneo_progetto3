"""Validate the catalogue, the knowledge base and the generated orders.

Everything checked here was verified by hand while the data was written; this script is
what stops it from drifting later. It exits non-zero on the first failing category, so
`make data` fails loudly rather than producing a quietly inconsistent knowledge base.

Run with: uv run python scripts/validate_data.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

import frontmatter
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
KB_DIR = REPO_ROOT / "data" / "kb"
CATALOG_PATH = REPO_ROOT / "data" / "catalog.yaml"
ORDERS_PATH = REPO_ROOT / "data" / "orders.json"

BUSINESS_DATE = dt.date(2026, 10, 12)
SKU_PATTERN = re.compile(r"^GT-[A-Z]{3}-\d{3}$")
DOC_TYPES = {"product", "guide", "policy"}
STATUSES = {
    "processing",
    "shipped",
    "delivered",
    "return_requested",
    "returned",
    "refunded",
    "cancelled",
}
MIN_WORDS, MAX_WORDS = 250, 700
MIN_ORDERS = 24
REQUIRED_DOCS = ("guides/bulbi_autunnali.md",)
# Internal cross-references are written as `folder/name.md` inside backticks.
LINK_PATTERN = re.compile(r"`((?:products|guides|policies)/[a-z0-9_]+\.md)`")


def _seasons() -> set[str]:
    """Return the valid season names, taken from the clock rather than duplicated.

    Returns:
        The set of Italian season names the system recognises.
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from greenthumb.clock import _SEASON_BY_MONTH

    return set(_SEASON_BY_MONTH.values())


def check_catalog(catalog: list[dict[str, Any]]) -> list[str]:
    """Check the catalogue's internal consistency.

    Args:
        catalog: The parsed product list.

    Returns:
        A list of human-readable errors, empty when the catalogue is valid.
    """
    errors: list[str] = []
    seasons = _seasons()
    required = {
        "sku",
        "name",
        "short_description",
        "category",
        "price_eur",
        "perishable",
        "season",
        "kb_path",
    }
    seen_skus: set[str] = set()
    seen_paths: set[str] = set()

    for product in catalog:
        sku = product.get("sku", "<senza sku>")
        missing = required - set(product)
        if missing:
            errors.append(f"{sku}: campi mancanti {sorted(missing)}")
            continue
        if not SKU_PATTERN.match(sku):
            errors.append(f"{sku}: formato SKU non valido, atteso GT-<CAT>-<NNN>")
        if sku in seen_skus:
            errors.append(f"{sku}: SKU duplicato")
        seen_skus.add(sku)
        if product["kb_path"] in seen_paths:
            errors.append(f"{sku}: kb_path duplicato {product['kb_path']}")
        seen_paths.add(product["kb_path"])
        if not product["kb_path"].endswith(".md"):
            errors.append(f"{sku}: kb_path senza estensione (ADR-006)")
        if not (KB_DIR / product["kb_path"]).exists():
            errors.append(f"{sku}: scheda prodotto assente ({product['kb_path']})")
        if not isinstance(product["price_eur"], int | float) or product["price_eur"] <= 0:
            errors.append(f"{sku}: prezzo non valido")
        bad = set(product["season"]) - seasons
        if bad or not product["season"]:
            errors.append(f"{sku}: stagioni non valide {sorted(bad) or 'vuote'}")
        perishable_expected = product["category"] in {"sementi", "bulbi"}
        if product["perishable"] != perishable_expected:
            errors.append(
                f"{sku}: perishable={product['perishable']} incoerente con "
                f"categoria {product['category']}"
            )
    return errors


def check_knowledge_base(catalog: list[dict[str, Any]]) -> list[str]:
    """Check every knowledge base document.

    Args:
        catalog: The parsed product list, used to validate SKU references.

    Returns:
        A list of human-readable errors, empty when the knowledge base is valid.
    """
    errors: list[str] = []
    seasons = _seasons()
    skus = {p["sku"] for p in catalog}
    by_path = {p["kb_path"]: p for p in catalog}
    paths = sorted(str(p.relative_to(KB_DIR)) for p in KB_DIR.rglob("*.md"))
    known = set(paths)

    for required_doc in REQUIRED_DOCS:
        if required_doc not in known:
            errors.append(f"documento obbligatorio assente: {required_doc}")

    for rel in paths:
        post = frontmatter.load(KB_DIR / rel)
        body = post.content
        words = len(body.split())

        if post.get("doc_id") != rel:
            errors.append(f"{rel}: doc_id={post.get('doc_id')!r} non coincide con il path")
        if post.get("doc_type") not in DOC_TYPES:
            errors.append(f"{rel}: doc_type non valido ({post.get('doc_type')!r})")
        if not str(post.get("title") or "").strip():
            errors.append(f"{rel}: title mancante")
        if not str(post.get("category") or "").strip():
            errors.append(f"{rel}: category mancante")
        if not MIN_WORDS <= words <= MAX_WORDS:
            errors.append(f"{rel}: {words} parole, fuori dall'intervallo {MIN_WORDS}-{MAX_WORDS}")

        unknown = set(post.get("related_skus") or []) - skus
        if unknown:
            errors.append(f"{rel}: related_skus inesistenti {sorted(unknown)}")

        season = post.get("season")
        if season is not None:
            bad = set(season) - seasons
            if bad or not season:
                errors.append(f"{rel}: stagioni non valide {sorted(bad) or 'vuote'}")

        for link in LINK_PATTERN.findall(body):
            if link not in known:
                errors.append(f"{rel}: riferimento interno rotto a {link}")

        product = by_path.get(rel)
        if product is not None:
            # Newline-tolerant: the source wraps at 100 columns, so a figure can straddle lines.
            flat = " ".join(body.split())
            price = f"{product['price_eur']:.2f}".replace(".", ",")
            if price not in flat:
                errors.append(f"{rel}: il prezzo di catalogo {price} non compare nella scheda")
            if post.get("category") != product["category"]:
                errors.append(f"{rel}: category diversa da quella del catalogo")
            if post.get("season") != product["season"]:
                errors.append(f"{rel}: season diversa da quella del catalogo")
            if product["sku"] not in (post.get("related_skus") or []):
                errors.append(f"{rel}: lo SKU del prodotto stesso manca da related_skus")

    for kb_path in by_path:
        if kb_path not in known:
            errors.append(f"scheda prodotto mancante: {kb_path}")
    return errors


def check_orders(catalog: list[dict[str, Any]]) -> list[str]:
    """Check the generated orders.

    Args:
        catalog: The parsed product list, used to validate SKUs and prices.

    Returns:
        A list of human-readable errors, empty when the orders are valid.
    """
    errors: list[str] = []
    if not ORDERS_PATH.exists():
        return [f"{ORDERS_PATH.name} non esiste: eseguire prima generate_orders.py"]

    orders = json.loads(ORDERS_PATH.read_text(encoding="utf-8"))
    prices = {p["sku"]: p["price_eur"] for p in catalog}
    names = {p["sku"]: p["name"] for p in catalog}

    if len(orders) < MIN_ORDERS:
        errors.append(f"{len(orders)} ordini, ne servono almeno {MIN_ORDERS}")

    seen: set[str] = set()
    per_status: dict[str, int] = {}
    for order in orders:
        oid = order.get("order_id", "<senza id>")
        if oid in seen:
            errors.append(f"ordine {oid}: identificativo duplicato")
        seen.add(oid)
        if not isinstance(oid, str) or not oid.isdigit():
            errors.append(f"ordine {oid}: l'identificativo deve essere una stringa numerica")

        status = order.get("status")
        if status not in STATUSES:
            errors.append(f"ordine {oid}: stato non valido ({status!r})")
        per_status[status] = per_status.get(status, 0) + 1

        if not order.get("items"):
            errors.append(f"ordine {oid}: nessun articolo")
        total = 0.0
        for item in order.get("items", []):
            sku = item.get("sku")
            if sku not in prices:
                errors.append(f"ordine {oid}: SKU inesistente {sku}")
                continue
            if item["unit_price_eur"] != prices[sku]:
                errors.append(
                    f"ordine {oid}: prezzo di {sku} ({item['unit_price_eur']}) "
                    f"diverso dal catalogo ({prices[sku]})"
                )
            if item.get("name") != names[sku]:
                errors.append(f"ordine {oid}: nome di {sku} diverso dal catalogo")
            if item.get("quantity", 0) < 1:
                errors.append(f"ordine {oid}: quantita non valida per {sku}")
            total += item["quantity"] * item["unit_price_eur"]
        if abs(round(total, 2) - order.get("total_eur", -1)) > 0.001:
            errors.append(
                f"ordine {oid}: totale {order.get('total_eur')} != somma righe {round(total, 2)}"
            )

        if status in {"return_requested", "returned", "refunded"} and not order.get("return"):
            errors.append(f"ordine {oid}: stato {status} senza oggetto return")
        if status in {"processing", "cancelled"} and order.get("return"):
            errors.append(f"ordine {oid}: stato {status} non dovrebbe avere un return")

    for status in sorted(STATUSES):
        if per_status.get(status, 0) < 2:
            errors.append(f"stato {status}: solo {per_status.get(status, 0)} ordini, ne servono 2")

    errors.extend(_check_traccia_order(orders))
    return errors


def _check_traccia_order(orders: list[dict[str, Any]]) -> list[str]:
    """Check order 1042 against the example fixed by SPEC section 4.4.

    Args:
        orders: The parsed order list.

    Returns:
        A list of human-readable errors, empty when order 1042 conforms.
    """
    errors: list[str] = []
    order = next((o for o in orders if o["order_id"] == "1042"), None)
    if order is None:
        return ["ordine 1042 assente: e' l'esempio della traccia"]
    if order["status"] != "shipped":
        errors.append(f"ordine 1042: stato {order['status']!r}, atteso 'shipped'")
    expected = (BUSINESS_DATE + dt.timedelta(days=1)).isoformat()
    if order["estimated_delivery"] != expected:
        errors.append(
            f"ordine 1042: consegna stimata {order['estimated_delivery']}, "
            f"attesa {expected} (business date + 1)"
        )
    if not any(i["sku"] == "GT-BUL-001" for i in order["items"]):
        errors.append("ordine 1042: deve contenere bulbi di tulipano GT-BUL-001")
    return errors


def main() -> int:
    """Run every check and report.

    Returns:
        0 when everything is valid, 1 otherwise.
    """
    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))["products"]

    sections = (
        ("catalogo", check_catalog(catalog)),
        ("knowledge base", check_knowledge_base(catalog)),
        ("ordini", check_orders(catalog)),
    )

    failed = False
    for name, errors in sections:
        if errors:
            failed = True
            print(f"\n[FALLITO] {name}: {len(errors)} problemi")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[ok] {name}")

    if failed:
        print("\nValidazione fallita.")
        return 1

    docs = sorted(KB_DIR.rglob("*.md"))
    orders = json.loads(ORDERS_PATH.read_text(encoding="utf-8"))
    print(
        f"\nValidazione superata: {len(catalog)} prodotti, {len(docs)} documenti, "
        f"{len(orders)} ordini."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
