import json
import xmlrpc.client
from functools import lru_cache

import pandas as pd
import streamlit as st


CONFIG_FILE = "config.json"


@lru_cache(maxsize=1)
def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_resource(show_spinner=False)
def connect_odoo(sys_key: str, conf: dict):
    """
    Connects to one Odoo instance via XML-RPC using API key as password.
    """
    url = conf["url"].rstrip("/")
    db = conf["db"]
    user = conf["user"]
    api_key = conf["api_key"]  # Odoo API key = password

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, api_key, {})
    if not uid:
        raise RuntimeError(f"Login failed for {sys_key} ({url})")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    return db, uid, api_key, models


def get_qty_for_models(sys_key: str, conf: dict, model_values, model_field: str):
    """
    Bulk fetch qty_available for list of model_values from one Odoo.
    Uses product.product search_read for performance.
    """
    if not model_values:
        return {}

    db, uid, pwd, models = connect_odoo(sys_key, conf)

    domain = [[model_field, "in", model_values]]
    products = models.execute_kw(
        db,
        uid,
        pwd,
        "product.product",
        "search_read",
        [domain],
        {
            "fields": ["id", model_field, "display_name", "qty_available"],
            "limit": 5000,
        },
    )

    result = {}
    for p in products:
        key = p.get(model_field)
        if key:
            result[key] = {
                "name": p.get("display_name", ""),
                "qty": float(p.get("qty_available", 0.0)),
            }
    return result


def main():
    st.set_page_config(
        page_title="Odoo Multi-DB Stock Compare",
        page_icon="👕",
        layout="wide",
    )

    cfg = load_config()
    swag = cfg["swag"]
    larouche = cfg["larouche"]
    diffc = cfg["different_clothes"]
    model_field_default = cfg.get("model_field", "default_code")

    # Sidebar
    st.sidebar.title("⚙️ Settings")
    st.sidebar.markdown("**Odoo Connections** (from config.json)")
    st.sidebar.write(f"✅ {swag['name']}")
    st.sidebar.write(f"✅ {larouche['name']}")
    st.sidebar.write(f"✅ {diffc['name']}")

    model_field = st.sidebar.text_input(
        "Model field (technical name)",
        value=model_field_default,
        help="e.g. default_code, x_model_no",
    )

    st.sidebar.info(
        "URLs, DB names, API keys config.json se aa rahe hain. "
        "Repo public karne se pehle config.json ko .gitignore karo."
    )

    # Main UI
    st.title("👕 3 Odoo Databases – Stock Comparison")
    st.caption("SWAG, La Rouche aur Different Clothes me same model ka stock compare karo.")

    col1, col2 = st.columns([2, 1])

    with col1:
        models_text = st.text_area(
            "Model numbers (har line me 1)",
            placeholder="MM0579\nMM0583\nMM0389",
            height=220,
        )

    with col2:
        st.markdown("**Kaise use kare**")
        st.markdown(
            "- Upar model numbers paste karo (default_code / x_model_no).\n"
            "- Neeche **Compare Quantities** button dabao.\n"
            "- Niche table me teeno Odoo ka stock side‑by‑side aayega."
        )
        include_zero = st.checkbox(
            "Zero quantity wale rows bhi dikhana hai", value=True
        )

    models_list = [
        m.strip()
        for m in models_text.splitlines()
        if m.strip()
    ]

    if st.button("🔍 Compare Quantities", type="primary"):
        if not models_list:
            st.warning("Pehle kam se kam 1 model number daalo.")
            st.stop()

        with st.spinner("Teeno Odoo se quantities nikal rahe hain..."):
            swag_map = get_qty_for_models("swag", swag, models_list, model_field)
            lrc_map = get_qty_for_models("larouche", larouche, models_list, model_field)
            diff_map = get_qty_for_models(
                "different_clothes", diffc, models_list, model_field
            )

        rows = []
        for m in models_list:
            s = swag_map.get(m, {})
            l = lrc_map.get(m, {})
            d = diff_map.get(m, {})

            swag_qty = s.get("qty", 0.0)
            lrc_qty = l.get("qty", 0.0)
            diff_qty = d.get("qty", 0.0)

            if not include_zero and (swag_qty == 0 and lrc_qty == 0 and diff_qty == 0):
                continue

            name = s.get("name") or l.get("name") or d.get("name") or ""
            rows.append(
                {
                    "Model": m,
                    "Product Name": name,
                    swag["name"]: swag_qty,
                    larouche["name"]: lrc_qty,
                    diffc["name"]: diff_qty,
                }
            )

        if not rows:
            st.info("Koi data nahi mila (shayad sab zero ya model mismatch).")
            st.stop()

        df = pd.DataFrame(rows)

        st.subheader("📊 Quantity Comparison")
        st.dataframe(
            df.style.format(
                {
                    swag["name"]: "{:.2f}",
                    larouche["name"]: "{:.2f}",
                    diffc["name"]: "{:.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Download as CSV",
            csv,
            file_name="odoo_multi_db_qty_compare.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
