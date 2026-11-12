"""
BhumiMitra Assam (ভূমি মিত্র অসম)
Post-harvest residual soil moisture and Rabi crop suitability after Sali paddy.

Run:  streamlit run app.py

Deploy secrets (.streamlit/secrets.toml or Streamlit Cloud > Secrets):
[gee]
type = "service_account"
project_id = "your-project"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "name@your-project.iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"

Register the service account for Earth Engine at
https://signup.earthengine.google.com/#!/service_accounts
"""
import json
from datetime import datetime, timezone

import ee
import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

st.set_page_config(page_title="BhumiMitra Assam", page_icon="🌾", layout="wide")

WINDOW_DAYS = 20
DISTRICTS = {
    "Darrang (Mangaldoi)": (26.44, 92.03), "Kamrup": (26.15, 91.75),
    "Nalbari": (26.45, 91.44), "Barpeta": (26.32, 91.00),
    "Morigaon": (26.25, 92.34), "Nagaon": (26.35, 92.68),
    "Sonitpur": (26.63, 92.80), "Golaghat": (26.52, 93.96),
    "Jorhat": (26.75, 94.20), "Lakhimpur": (27.24, 94.10),
    "Dhemaji": (27.48, 94.58), "Dibrugarh": (27.48, 94.91),
    "Goalpara": (26.17, 90.62), "Cachar": (24.83, 92.78),
}
ZONE_COLOR = {1: "#1a9850", 2: "#f2c230", 3: "#d9822b"}

T = {
    "en": {
        "title": "BhumiMitra Assam",
        "sub": "Residual soil moisture and Rabi crop guide after Sali paddy",
        "lang": "Language", "district": "District / area",
        "how": "Click a point or draw a polygon around your plot on the map.",
        "adv": "Advanced thresholds (officers)",
        "z": {1: "Zone 1: High residual moisture",
              2: "Zone 2: Moderate moisture",
              3: "Zone 3: Dry / sandy soil"},
        "rec": {1: "Good for zero-irrigation Mustard, Lentil or Pea.",
                2: "Suitable for Rabi vegetables or potato with 1 light irrigation.",
                3: "Low moisture or flood-deposited sand. Use mulching or irrigate before sowing."},
        "conf": {"High": "High Confidence", "Medium": "Medium Confidence", "Low": "Low Confidence"},
        "pass": "Clear satellite pass {d} days ago", "nopass": "No recent clear pass",
        "tech": "Technical Details", "dl": "Download summary report",
        "none": "No clear cropland pixels found for this plot in the last 20 days. Try a bigger plot or check back later.",
        "legend": "Map colours", "plot": "Your plot", "area": "Area (ha)",
        "note": "Advisory only. Thresholds are indicative; confirm with a field check.",
    },
    "as": {
        "title": "ভূমি মিত্ৰ অসম",
        "sub": "শালি ধান দাৱনীৰ পিছত মাটিৰ অৱশিষ্ট আৰ্দ্ৰতা আৰু ৰবি শস্যৰ পৰামৰ্শ",
        "lang": "ভাষা", "district": "জিলা / এলেকা",
        "how": "মানচিত্ৰত এটা বিন্দুত ক্লিক কৰক বা আপোনাৰ খেতিপথাৰৰ চাৰিওফালে পলিগন আঁকক।",
        "adv": "উন্নত সীমা (বিষয়াসকলৰ বাবে)",
        "z": {1: "ক্ষেত্ৰ ১: উচ্চ অৱশিষ্ট আৰ্দ্ৰতা",
              2: "ক্ষেত্ৰ ২: মধ্যম আৰ্দ্ৰতা",
              3: "ক্ষেত্ৰ ৩: শুকান / বালিময় মাটি"},
        "rec": {1: "জলসিঞ্চন নোহোৱাকৈ সৰিয়হ, মচুৰ বা মটৰ খেতিৰ বাবে উপযুক্ত।",
                2: "এবাৰ পাতল জলসিঞ্চনেৰে ৰবি পাচলি বা আলু খেতিৰ বাবে উপযুক্ত।",
                3: "আৰ্দ্ৰতা কম বা বানে অনা বালি। বীজ সিঁচাৰ আগতে মালচিং বা জলসিঞ্চন কৰক।"},
        "conf": {"High": "উচ্চ আস্থা", "Medium": "মধ্যম আস্থা", "Low": "কম আস্থা"},
        "pass": "{d} দিন আগতে স্পষ্ট উপগ্ৰহ পাস", "nopass": "শেহতীয়া স্পষ্ট উপগ্ৰহ পাস নাই",
        "tech": "প্ৰযুক্তিগত তথ্য", "dl": "সাৰাংশ প্ৰতিবেদন ডাউনলোড কৰক",
        "none": "যোৱা ২০ দিনত এই খেতিপথাৰত স্পষ্ট পিক্সেল পোৱা নগ'ল। ডাঙৰ এলেকা বাছক বা পিছত চাওক।",
        "legend": "মানচিত্ৰৰ ৰং", "plot": "আপোনাৰ খেতিপথাৰ", "area": "কালি (হেক্টৰ)",
        "note": "এয়া কেৱল পৰামৰ্শ। সীমাবোৰ আনুমানিক; পথাৰত পৰীক্ষা কৰি নিশ্চিত কৰক।",
    },
}


# ---------- Earth Engine ----------
@st.cache_resource
def init_ee():
    try:
        if "gee_json" in st.secrets:
            creds = json.loads(st.secrets["gee_json"])
        else:
            creds = dict(st.secrets["gee"])
        c = ee.ServiceAccountCredentials(creds["client_email"], key_data=json.dumps(creds))
        ee.Initialize(c, project=creds.get("project_id"))
    except Exception:
        ee.Initialize()  # local dev: earthengine authenticate
    return True


def build_layers(th):
    """Return dict of EE images for the last 20 days."""
    hi, lo, bsit = th
    now = datetime.now(timezone.utc)
    end = ee.Date(now.strftime("%Y-%m-%d")).advance(1, "day")
    start = end.advance(-WINDOW_DAYS - 1, "day")
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterDate(start, end)
           .filterBounds(ee.Geometry.Rectangle([89.7, 24.1, 96.1, 28.3])))

    def prep(img):
        scl = img.select("SCL")
        clear = scl.eq(4).Or(scl.eq(5))  # vegetation or bare soil only
        r = img.select(["B2", "B3", "B4", "B8", "B11"]).divide(10000)
        ndmi = r.normalizedDifference(["B8", "B11"]).rename("NDMI")
        ndwi = r.normalizedDifference(["B3", "B8"]).rename("NDWI")
        bsi = r.expression(
            "((s + red) - (nir + blue)) / ((s + red) + (nir + blue))",
            {"s": r.select("B11"), "red": r.select("B4"),
             "nir": r.select("B8"), "blue": r.select("B2")}).rename("BSI")
        t = ee.Image.constant(img.date().millis()).toFloat().rename("t")
        return ee.Image.cat([ndmi, ndwi, bsi, t]).updateMask(clear)

    c = col.map(prep)
    med = c.select(["NDMI", "NDWI", "BSI"]).median()
    n = c.select("NDMI").count().rename("n")
    last = c.select("t").max().rename("t")
    crop = (ee.ImageCollection("ESA/WorldCover/v200").first()
            .select("Map").eq(40))  # cropland

    ndmi, bsi = med.select("NDMI"), med.select("BSI")
    zone = (ee.Image(2)
            .where(ndmi.gte(hi).And(bsi.lt(bsit)), 1)
            .where(ndmi.lt(lo).Or(bsi.gte(bsit)), 3)
            .updateMask(ndmi.mask()).updateMask(crop).rename("zone"))
    age = ee.Image.constant(now.timestamp() * 1000).subtract(last).divide(86400000)
    conf = (n.divide(5).min(1).multiply(60)
            .add(ee.Image(1).subtract(age.divide(WINDOW_DAYS)).max(0).multiply(40))
            .updateMask(ndmi.mask()).updateMask(crop).rename("conf"))
    stack = ee.Image.cat([med.updateMask(crop), n, last])
    return {"zone": zone, "conf": conf, "stack": stack}


@st.cache_data(ttl=3600, show_spinner=False)
def tile_urls(th):
    L = build_layers(th)
    z = L["zone"].getMapId({"min": 1, "max": 3, "palette": [ZONE_COLOR[1], ZONE_COLOR[2], ZONE_COLOR[3]]})
    c = L["conf"].getMapId({"min": 0, "max": 100, "palette": ["#d73027", "#fee08b", "#1a9850"]})
    return z["tile_fetcher"].url_format, c["tile_fetcher"].url_format


@st.cache_data(ttl=3600, show_spinner=False)
def plot_stats(geojson_str, th):
    geom = ee.Geometry(json.loads(geojson_str))
    s = build_layers(th)["stack"]
    mean = s.select(["NDMI", "NDWI", "BSI", "n"]).reduceRegion(
        ee.Reducer.mean(), geom, 10, bestEffort=True, maxPixels=1e8)
    mx = s.select("t").reduceRegion(ee.Reducer.max(), geom, 10, bestEffort=True, maxPixels=1e8)
    out = ee.Dictionary(mean).combine(mx).set("area", geom.area(1).divide(10000))
    return out.getInfo()


# ---------- Logic ----------
def classify(ndmi, bsi, th):
    hi, lo, bsit = th
    if ndmi < lo or bsi >= bsit:
        return 3
    if ndmi >= hi:
        return 1
    return 2


def confidence(stats):
    n, t = stats.get("n"), stats.get("t")
    if not n or not t:
        return 0, None
    age = max(0.0, (datetime.now(timezone.utc).timestamp() * 1000 - t) / 86400000)
    score = min(n / 5, 1) * 60 + max(0, 1 - age / WINDOW_DAYS) * 40
    return round(score), int(round(age))


def level(p):
    return "High" if p >= 75 else "Medium" if p >= 50 else "Low"


def report(lang, tx, zone, pct, age, st_):
    lines = [
        "BhumiMitra Assam - " + tx["plot"],
        f"Date: {datetime.now().strftime('%d %b %Y')}", "",
        tx["z"][zone], tx["rec"][zone], "",
        f"{tx['conf'][level(pct)]} ({pct}%) - "
        + (tx["pass"].format(d=age) if age is not None else tx["nopass"]), "",
        tx["tech"],
        f"NDMI: {st_['NDMI']:.3f}", f"NDWI: {st_['NDWI']:.3f}", f"BSI: {st_['BSI']:.3f}",
        f"Clear observations (last {WINDOW_DAYS} d): {st_['n']:.1f}",
        f"{tx['area']}: {st_['area']:.2f}", "",
        "Source: Sentinel-2 SR Harmonized, ESA WorldCover v200 cropland mask.", tx["note"],
    ]
    return "\n".join(lines)


# ---------- UI ----------
init_ee()
lang = st.sidebar.radio("Language / ভাষা", ["English", "অসমীয়া"], horizontal=True)
tx = T["en" if lang == "English" else "as"]

st.title("🌾 " + tx["title"])
st.caption(tx["sub"])

district = st.sidebar.selectbox(tx["district"], list(DISTRICTS))
with st.sidebar.expander(tx["adv"]):
    hi = st.slider("NDMI high moisture >=", -0.2, 0.4, 0.10, 0.01)
    lo = st.slider("NDMI dry <", -0.3, 0.2, -0.05, 0.01)
    bsit = st.slider("BSI dry >=", -0.1, 0.4, 0.15, 0.01)
th = (hi, lo, bsit)

lat, lon = DISTRICTS[district]
zurl, curl = tile_urls(th)

m = folium.Map(location=[lat, lon], zoom_start=12, control_scale=True)
folium.TileLayer("Esri.WorldImagery", name="Satellite", show=False).add_to(m)
folium.TileLayer(zurl, attr="Google Earth Engine / Copernicus", name="Suitability zones", overlay=True).add_to(m)
folium.TileLayer(curl, attr="Google Earth Engine", name="Confidence", overlay=True, show=False).add_to(m)
Draw(export=False, draw_options={"polyline": False, "circle": False, "circlemarker": False,
                                 "rectangle": False, "marker": True, "polygon": True}).add_to(m)
folium.LayerControl().add_to(m)

st.info(tx["how"])
out = st_folium(m, height=480, use_container_width=True, key=f"map_{district}",
                returned_objects=["last_active_drawing", "last_clicked"])

# legend
st.markdown(tx["legend"] + ": " + " ".join(
    f"<span style='background:{ZONE_COLOR[k]};color:#fff;padding:2px 8px;border-radius:6px;margin-right:4px'>{k}</span>"
    for k in (1, 2, 3)), unsafe_allow_html=True)

geom = None
d = (out or {}).get("last_active_drawing")
if d and d.get("geometry"):
    g = d["geometry"]
    if g["type"] == "Point":
        geom = ee.Geometry.Point(g["coordinates"]).buffer(30).getInfo()
    else:
        geom = g
elif (out or {}).get("last_clicked"):
    c = out["last_clicked"]
    geom = ee.Geometry.Point([c["lng"], c["lat"]]).buffer(30).getInfo()

if geom:
    with st.spinner("..."):
        s = plot_stats(json.dumps(geom), th)
    if s.get("NDMI") is None or s.get("n") is None:
        st.warning(tx["none"])
    else:
        zone = classify(s["NDMI"], s["BSI"], th)
        pct, age = confidence(s)
        lvl = level(pct)
        col = ZONE_COLOR[zone]
        badge_col = {"High": "#1a9850", "Medium": "#b8860b", "Low": "#c0392b"}[lvl]
        pass_txt = tx["pass"].format(d=age) if age is not None else tx["nopass"]
        st.markdown(
            f"<div style='border-left:10px solid {col};padding:14px 16px;border-radius:8px;"
            f"background:{col}22'><h3 style='margin:0'>{tx['z'][zone]}</h3>"
            f"<p style='font-size:1.1rem;margin:.5rem 0'>{tx['rec'][zone]}</p>"
            f"<span style='background:{badge_col};color:#fff;padding:4px 10px;border-radius:12px;"
            f"font-size:.9rem'>{tx['conf'][lvl]} ({pct}%) · {pass_txt}</span></div>",
            unsafe_allow_html=True)
        with st.expander(tx["tech"]):
            st.table({"NDMI": [f"{s['NDMI']:.3f}"], "NDWI": [f"{s['NDWI']:.3f}"],
                      "BSI": [f"{s['BSI']:.3f}"], "Clear obs": [f"{s['n']:.1f}"],
                      tx["area"]: [f"{s['area']:.2f}"]})
        st.download_button(tx["dl"], report(lang, tx, zone, pct, age, s),
                           file_name="bhumimitra_report.txt", mime="text/plain")
st.caption(tx["note"])
