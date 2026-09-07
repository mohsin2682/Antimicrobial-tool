import re
from datetime import datetime

import requests
import streamlit as st

st.set_page_config(page_title="Antimicrobial Stewardship", layout="wide", page_icon="🧫")

# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = []
if "pcn_allergy" not in st.session_state:
    st.session_state.pcn_allergy = False
if "compare_mode" not in st.session_state:
    st.session_state.compare_mode = False

# ---------------------------------------------------------------------------
# LIGHTWEIGHT STYLING (badge pills used for the "quick facts" row)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .badge {
        display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:0.85rem; font-weight:600; margin:2px 6px 2px 0;
        border:1px solid rgba(128,128,128,0.35);
    }
    .badge-green  { background:rgba(46,160,67,0.15); color:#2ea043; }
    .badge-yellow { background:rgba(210,153,34,0.15); color:#d29922; }
    .badge-red    { background:rgba(248,81,73,0.15); color:#f85149; }
    .badge-grey   { background:rgba(128,128,128,0.15); color:#8b949e; }
    </style>
    """,
    unsafe_allow_html=True,
)


def badge(label, tone="grey"):
    return f'<span class="badge badge-{tone}">{label}</span>'


# ---------------------------------------------------------------------------
# CLINICAL DATABASE
# Each entry additionally carries `drug_class` and `coverage` (structured
# organism tags) so the app can filter/search/compare on them, not just
# display free text.
# ---------------------------------------------------------------------------
ANTIMICROBIALS = {
    "amoxicillin": {
        "generic": "Amoxicillin", "brand": "Amoxil",
        "drug_class": "Aminopenicillin (Penicillin)",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (penicillin class, bactericidal).",
        "spectrum": "✅ Gram-positive (Strep, Enterococcus). ✅ Limited Gram-negative (E. coli, H. influenzae). ❌ No anaerobes.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "Sinusitis, Otitis Media, Strep Pharyngitis, CAP, UTI, Dental prophylaxis.",
        "side_effects": "Diarrhea, nausea, rash. Risk of C. diff. Anaphylaxis in true PCN allergy.",
        "pregnancy": "Category B. Generally considered safe.",
        "cross_allergy": "⚠️ Cross-reacts with cephalosporins (low ~5-10%). Avoid if true anaphylaxis to PCN.",
        "bioavailability": "Oral: ~80%. Protein binding: ~20%.",
        "max_duration": "7-10 days (Uncomplicated UTI: 3-5 days).",
        "dosing_adults": "500 mg PO q8h OR 875 mg PO q12h.",
        "dosing_peds": "20-45 mg/kg/day PO divided q8-12h (Max 875 mg/dose).",
        "dosing_renal": "CrCl < 10 mL/min: Extend interval to q24h.",
        "pharmacist_notes": "✅ Can be crushed/split. Suspension must be refrigerated. Take with food to reduce GI upset.",
    },
    "azithromycin": {
        "generic": "Azithromycin", "brand": "Zithromax",
        "drug_class": "Macrolide",
        "mechanism": "Macrolide; binds 50S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Gram-positive (Strep, Staph). ✅ Atypicals (Chlamydia, Mycoplasma). ✅ Some Gram-negative (H. flu).",
        "coverage": ["Gram-positive", "Atypicals", "Gram-negative (limited)"],
        "indications": "CAP, AECB, Sinusitis, Strep (PCN-allergic), STIs (Chlamydia/Gonorrhea).",
        "side_effects": "Diarrhea, nausea, QT prolongation (dose-dependent), hepatotoxicity.",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~37%. Protein binding: ~50%.",
        "max_duration": "5-day Z-Pak OR 2g single dose for chlamydia.",
        "dosing_adults": "500mg day 1, then 250mg days 2-5. Or 2g single dose.",
        "dosing_peds": "10 mg/kg day 1, then 5 mg/kg days 2-5 (Max 500mg/250mg).",
        "dosing_renal": "No adjustment needed.",
        "pharmacist_notes": "✅ IV compatible with NS/D5W (infuse over 1 hr). Can take with food. Caution in known QT prolongation.",
    },
    "ciprofloxacin": {
        "generic": "Ciprofloxacin", "brand": "Cipro",
        "drug_class": "Fluoroquinolone",
        "mechanism": "Fluoroquinolone; inhibits DNA gyrase (topoisomerase II), bactericidal.",
        "spectrum": "✅ Strong Gram-negative (Pseudomonas, Enterobacter, E. coli). ⚠️ Moderate Gram-positive (Staph). ❌ No anaerobes.",
        "coverage": ["Gram-negative", "Pseudomonas", "Gram-positive (moderate)"],
        "indications": "Complicated UTIs, Pyelonephritis, Prostatitis, Bone/Joint infections, Anthrax.",
        "side_effects": "⚠️ Tendon rupture (Achilles). Peripheral neuropathy. CNS agitation. QT prolongation.",
        "pregnancy": "Category C. Avoid in pregnancy/breastfeeding.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~70%. Protein binding: ~25%.",
        "max_duration": "UTI: 3-7 days. Prostatitis: 28 days. Osteomyelitis: 4-6 weeks.",
        "dosing_adults": "250-750 mg PO q12h. IV: 400 mg q12h.",
        "dosing_peds": "Only for specific indications: 10-20 mg/kg/dose PO q12h (Max 750 mg).",
        "dosing_renal": "CrCl 30-50: 250-500 mg q12h. CrCl <30: 250-500 mg q18-24h.",
        "pharmacist_notes": "🚫 Avoid in children <18 unless specific indication. ☕ Avoid dairy/antacids/iron/zinc within 2 hours. Hold dose 24h before/after IV contrast.",
    },
    "doxycycline": {
        "generic": "Doxycycline", "brand": "Vibramycin",
        "drug_class": "Tetracycline",
        "mechanism": "Tetracycline; binds 30S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Atypicals (Chlamydia, Mycoplasma, Rickettsia). ✅ MRSA (some). ✅ Gram-negative (some).",
        "coverage": ["Atypicals", "MRSA (some)", "Gram-negative (limited)"],
        "indications": "Skin/soft tissue infections, CAP (atypical), Lyme disease, RMSF, Malaria prophylaxis.",
        "side_effects": "Photosensitivity (sunburn risk), esophageal ulceration, tooth discoloration (if age <8).",
        "pregnancy": "Category D. Avoid (affects fetal bone/teeth).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >90%. Protein binding: ~90%.",
        "max_duration": "Lyme: 10-21 days. CAP: 7-10 days.",
        "dosing_adults": "100 mg PO/IV q12h (Loading: 200 mg day 1).",
        "dosing_peds": ">8 yrs: 2.2 mg/kg/dose q12h. <8 yrs: Avoid.",
        "dosing_renal": "No adjustment needed.",
        "pharmacist_notes": "☕ Swallow with full glass of water; remain upright for 30 min. Can take with food. 🚫 Avoid in children <8 and pregnant women.",
    },
    "metronidazole": {
        "generic": "Metronidazole", "brand": "Flagyl",
        "drug_class": "Nitroimidazole",
        "mechanism": "Nitroimidazole; disrupts DNA and protein synthesis in anaerobes (bactericidal).",
        "spectrum": "✅ Excellent anaerobes (Bacteroides, Clostridium). ✅ Some protozoa (Trichomonas, Giardia). ❌ No aerobes.",
        "coverage": ["Anaerobes", "Protozoa"],
        "indications": "Intra-abdominal infections, C. difficile, Bacterial vaginosis, Trichomoniasis.",
        "side_effects": "Metallic taste, nausea, peripheral neuropathy (long-term), disulfiram-like reaction with alcohol.",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >95%. Protein binding: <20%.",
        "max_duration": "C. diff: 10-14 days. Intra-abdominal: 7-10 days.",
        "dosing_adults": "500 mg PO q8h (or 250 mg q6h). IV: 500 mg q6-8h.",
        "dosing_peds": "7.5 mg/kg/dose PO/IV q6h (Max 500 mg).",
        "dosing_renal": "CrCl <10: Half dose (IV only, no adjustment for PO).",
        "pharmacist_notes": "🚫 ABSOLUTELY NO ALCOHOL during therapy and 48 hrs after (disulfiram). ☕ Take with food.",
    },
    "vancomycin": {
        "generic": "Vancomycin", "brand": "Vancocin",
        "drug_class": "Glycopeptide",
        "mechanism": "Glycopeptide; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ MRSA (strong). ✅ Gram-positive (Strep, Enterococcus). ❌ No Gram-negative.",
        "coverage": ["MRSA", "Gram-positive"],
        "indications": "MRSA infections, C. difficile (PO only), Endocarditis, Meningitis.",
        "side_effects": "Nephrotoxicity, Ototoxicity, Red Man Syndrome (rapid IV), thrombophlebitis.",
        "pregnancy": "Category C. Use if clearly needed (monitor levels).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: 0% (PO only for C. diff). IV: 100%. Protein binding: ~55%.",
        "max_duration": "MRSA bacteremia: 14 days minimum. C. diff: 10 days.",
        "dosing_adults": "PO: 125-500 mg q6h. IV: 15-20 mg/kg q8-12h (AUC-guided preferred).",
        "dosing_peds": "IV: 10-15 mg/kg/dose q6h. PO: 10 mg/kg/dose q6h (Max 125 mg for C. diff).",
        "dosing_renal": "Extend interval based on CrCl (e.g., q24-48h for severe renal impairment).",
        "pharmacist_notes": "🚨 IV must be infused over ≥60 min (prevents Red Man). 🩸 Monitor trough levels (10-20 mg/L for MRSA) or AUC. PO route is ONLY for C. difficile.",
    },
    "ceftriaxone": {
        "generic": "Ceftriaxone", "brand": "Rocephin",
        "drug_class": "Cephalosporin (3rd gen)",
        "mechanism": "3rd generation cephalosporin; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Broad Gram-negative (Neisseria, E. coli, Klebsiella). ✅ Moderate Gram-positive (Strep). ❌ No anaerobes.",
        "coverage": ["Gram-negative", "Gram-positive (moderate)"],
        "indications": "CAP, Gonorrhea, Intra-abdominal, Meningitis, Lyme (neuro).",
        "side_effects": "Diarrhea, biliary sludge (especially children), C. diff risk. Eosinophilia.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Caution in severe PCN allergy (cross-reactivity ~5%). Avoid if anaphylaxis.",
        "bioavailability": "IV/IM only. Protein binding: ~95%.",
        "max_duration": "CAP: 7-10 days. Meningitis: 14-21 days. Gonorrhea: Single dose.",
        "dosing_adults": "1-2 g IV/IM q24h (Gonorrhea: 500mg IM single dose).",
        "dosing_peds": "50-75 mg/kg IV/IM q24h (Max 2g). Meningitis: 80-100 mg/kg q12-24h.",
        "dosing_renal": "No adjustment needed (biliary excretion).",
        "pharmacist_notes": "✅ IM can be mixed with Lidocaine for pain. 🚫 Do NOT mix with Calcium-containing IV solutions (precipitate in neonates).",
    },
    "gentamicin": {
        "generic": "Gentamicin", "brand": "Generic",
        "drug_class": "Aminoglycoside",
        "mechanism": "Aminoglycoside; binds 30S ribosome, inhibits protein synthesis (bactericidal, concentration-dependent).",
        "spectrum": "✅ Strong Gram-negative (Pseudomonas, E. coli, Enterobacter). ✅ Synergy with beta-lactams for Enterococcus. ❌ No anaerobes.",
        "coverage": ["Gram-negative", "Pseudomonas", "Enterococcus (synergy)"],
        "indications": "Gram-negative sepsis, UTI, Endocarditis (synergy), Neutropenic fever.",
        "side_effects": "Nephrotoxicity (ATN), Ototoxicity (vestibular/cochlear), Neuromuscular blockade.",
        "pregnancy": "Category D. Avoid unless life-saving.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV/IM only. Protein binding: <10%.",
        "max_duration": "7-14 days (prolonged use increases toxicity risk).",
        "dosing_adults": "Traditional: 1-1.7 mg/kg IV/IM q8h. Extended: 5-7 mg/kg IV q24h.",
        "dosing_peds": "2.5 mg/kg IV q8h (Neonates: 2.5 mg/kg q12h).",
        "dosing_renal": "⛔ CRITICAL adjustment. Extend interval based on CrCl (e.g., q12h if CrCl 30-70, q24-48h if <30).",
        "pharmacist_notes": "🩸 Mandatory trough (<1-2 mg/L) and peak (5-10 mg/L) monitoring. Monitor BUN/Cr q2-3 days. Infuse over 30-60 min. Avoid loop diuretics.",
    },
    "piperacillin_tazobactam": {
        "generic": "Piperacillin-Tazobactam", "brand": "Zosyn",
        "drug_class": "Beta-lactam/Beta-lactamase inhibitor",
        "mechanism": "Penicillin + beta-lactamase inhibitor; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Broad: Gram-positive, Gram-negative (including Pseudomonas), and Anaerobes (Bacteroides).",
        "coverage": ["Gram-positive", "Gram-negative", "Pseudomonas", "Anaerobes"],
        "indications": "Severe intra-abdominal, skin, pneumonia. Empiric coverage for Pseudomonas.",
        "side_effects": "Diarrhea, headache, thrombocytopenia, neutropenia. Bleeding risk (platelet dysfunction).",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Penicillin-class. Avoid if severe PCN anaphylaxis.",
        "bioavailability": "IV only. Protein binding: ~30%.",
        "max_duration": "7-14 days based on cultures.",
        "dosing_adults": "3.375 g IV q6h OR 4.5 g IV q8h (Extended infusion preferred for Pseudomonas).",
        "dosing_peds": "80-100 mg/kg/dose IV q6-8h (piperacillin component).",
        "dosing_renal": "CrCl 20-40: 2.25 g IV q6h. CrCl <20: 2.25 g IV q8h.",
        "pharmacist_notes": "✅ Extended infusion (4.5g over 4 hrs) recommended for severe Pseudomonas. ⚠️ Contains Sodium (~2.5 mEq/g) - monitor in CHF.",
    },
    "clindamycin": {
        "generic": "Clindamycin", "brand": "Cleocin",
        "drug_class": "Lincosamide",
        "mechanism": "Lincosamide; binds 50S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Gram-positive (Strep, Staph, including some MRSA). ✅ Excellent anaerobes (Bacteroides, Clostridium). ❌ No Gram-negative.",
        "coverage": ["Gram-positive", "MRSA (some)", "Anaerobes"],
        "indications": "Skin/soft tissue infections (MRSA), aspiration pneumonia, dental infections, anaerobic infections.",
        "side_effects": "⚠️ High risk of C. difficile infection (~10-20%). Diarrhea, rash, hepatotoxicity.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~90%. Protein binding: ~90%.",
        "max_duration": "7-10 days (prolonged use increases C. diff risk).",
        "dosing_adults": "300-450 mg PO q6-8h. IV: 600-900 mg q8h.",
        "dosing_peds": "10-20 mg/kg/dose PO/IV q6-8h (Max 600 mg/dose).",
        "dosing_renal": "No adjustment needed.",
        "pharmacist_notes": "✅ IV compatible with NS/D5W (infuse over 10-60 min). 🚨 Be highly vigilant for C. diff diarrhea. Can cause esophagitis if not swallowed with water.",
    },
    "sulfamethoxazole_trimethoprim": {
        "generic": "Sulfamethoxazole-Trimethoprim", "brand": "Bactrim",
        "drug_class": "Sulfonamide combination",
        "mechanism": "Sequential blockade of bacterial folate synthesis (sulfamethoxazole inhibits dihydropteroate synthase, trimethoprim inhibits dihydrofolate reductase); synergistic and bactericidal.",
        "spectrum": "✅ MRSA (good). ✅ Gram-negative (E. coli, Proteus). ✅ Pneumocystis jirovecii. ❌ Pseudomonas. ❌ Most anaerobes.",
        "coverage": ["MRSA", "Gram-negative", "Atypicals (PJP)"],
        "indications": "Uncomplicated UTI, MRSA skin/soft tissue infections, PJP prophylaxis/treatment, traveler's diarrhea, Stenotrophomonas.",
        "side_effects": "Rash (including rare SJS/TEN), hyperkalemia, nephrotoxicity, bone marrow suppression, hemolysis in G6PD deficiency.",
        "pregnancy": "Category D. Avoid near term (kernicterus risk) and in 1st trimester (folate antagonist).",
        "cross_allergy": "Sulfonamide allergy — avoid. No beta-lactam cross-reactivity.",
        "bioavailability": "Oral: ~90-100%. Protein binding: ~70% (sulfamethoxazole) / ~45% (trimethoprim).",
        "max_duration": "UTI: 3-5 days. MRSA SSTI: 5-10 days. PJP treatment: 21 days.",
        "dosing_adults": "1 DS tablet (800/160mg) PO q12h (UTI/SSTI). PJP treatment: 15-20 mg/kg/day TMP component, divided q6-8h.",
        "dosing_peds": "8-12 mg/kg/day (TMP component) PO divided q12h.",
        "dosing_renal": "CrCl 15-30: Reduce dose 50%. CrCl <15: Avoid or use with intensive monitoring.",
        "pharmacist_notes": "🩸 Monitor potassium and renal function, especially with ACEi/ARB or in elderly patients. ☀️ Photosensitivity. 🚫 Avoid in G6PD deficiency and near-term pregnancy.",
    },
    "linezolid": {
        "generic": "Linezolid", "brand": "Zyvox",
        "drug_class": "Oxazolidinone",
        "mechanism": "Binds the 23S rRNA of the 50S ribosomal subunit, blocking initiation of protein synthesis (bacteriostatic).",
        "spectrum": "✅ MRSA (excellent). ✅ VRE (excellent — one of few oral options). ✅ Gram-positive. ❌ No Gram-negative.",
        "coverage": ["MRSA", "VRE", "Gram-positive"],
        "indications": "VRE infections, MRSA pneumonia (nosocomial/HAP/VAP), complicated skin/soft tissue infections.",
        "side_effects": "⚠️ Thrombocytopenia/myelosuppression (courses >2 weeks), peripheral & optic neuropathy (prolonged use), serotonin syndrome (with SSRIs/MAOIs), rare lactic acidosis.",
        "pregnancy": "Category C. Use only if benefit outweighs risk.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~100% (complete). Protein binding: ~31%.",
        "max_duration": "Generally ≤28 days; courses >2 weeks increase myelosuppression/neuropathy risk — monitor CBC weekly.",
        "dosing_adults": "600 mg PO/IV q12h.",
        "dosing_peds": "10 mg/kg/dose PO/IV q8h (Max 600 mg/dose).",
        "dosing_renal": "No adjustment needed (hepatic metabolism); active metabolites can accumulate in severe renal impairment — monitor.",
        "pharmacist_notes": "🚨 Weak MAOI — serotonin syndrome risk with SSRIs/SNRIs/MAOIs/triptans; avoid or use extreme caution. 🩸 Baseline + weekly CBC if course exceeds 2 weeks.",
    },
}

# Brand -> canonical dict key. Also used to resolve free-text/online lookups.
BRAND_MAP = {
    "amoxil": "amoxicillin",
    "zithromax": "azithromycin",
    "cipro": "ciprofloxacin",
    "vibramycin": "doxycycline",
    "flagyl": "metronidazole",
    "vancocin": "vancomycin",
    "rocephin": "ceftriaxone",
    "zosyn": "piperacillin_tazobactam",
    "cleocin": "clindamycin",
    "bactrim": "sulfamethoxazole_trimethoprim",
    "septra": "sulfamethoxazole_trimethoprim",
    "zyvox": "linezolid",
}

ALL_CLASSES = sorted({d["drug_class"] for d in ANTIMICROBIALS.values()})
ALL_COVERAGE = sorted({tag for d in ANTIMICROBIALS.values() for tag in d["coverage"]})
KEY_BY_LABEL = {f"{d['generic']} ({d['brand']})": k for k, d in ANTIMICROBIALS.items()}

FIELD_LABELS = [
    ("drug_class", "Drug class"),
    ("spectrum", "Spectrum of activity"),
    ("indications", "Indications"),
    ("dosing_adults", "Adult dosing"),
    ("dosing_peds", "Pediatric dosing"),
    ("dosing_renal", "Renal/hepatic adjustment"),
    ("side_effects", "Side effects"),
    ("pregnancy", "Pregnancy category"),
    ("cross_allergy", "Cross-allergy risk"),
    ("max_duration", "Max treatment duration"),
    ("pharmacist_notes", "Pharmacist notes"),
]

BETA_LACTAM_CLASSES = {"Aminopenicillin (Penicillin)", "Beta-lactam/Beta-lactamase inhibitor"}
CEPHALOSPORIN_CLASSES = {"Cephalosporin (3rd gen)"}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def label_for(key):
    d = ANTIMICROBIALS[key]
    return f"{d['generic']} ({d['brand']})"


def remember_lookup(display_name):
    hist = st.session_state.history
    if display_name in hist:
        hist.remove(display_name)
    hist.insert(0, display_name)
    st.session_state.history = hist[:5]


def jump_to_drug(display_name):
    """Button on_click callback. Callbacks run BEFORE the script reruns and
    widgets re-instantiate, so this is the safe way to change another
    widget's value programmatically (doing it after the widget has already
    rendered in the same pass raises StreamlitWidgetAlreadyInstantiatedError)."""
    st.session_state.filter_classes = []
    st.session_state.filter_coverage = []
    st.session_state.compare_mode = False
    st.session_state.drug_select = KEY_BY_LABEL.get(display_name)


def cockcroft_gault(age, weight_kg, scr, is_female):
    if age <= 0 or weight_kg <= 0 or scr <= 0:
        return None
    crcl = ((140 - age) * weight_kg) / (72 * scr)
    if is_female:
        crcl *= 0.85
    return crcl


def fetch_from_openfda(search_term):
    """Look up a drug directly from the FDA label API (used only for drugs
    NOT in the curated ANTIMICROBIALS dict — it never overrides curated data)."""
    clean_term = search_term.strip().lower()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AntimicrobialRef/1.0)"}
    query = f'openfda.generic_name:"{clean_term}"'
    url = "https://api.fda.gov/drug/label.json"

    try:
        response = requests.get(url, params={"search": query, "limit": 1}, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data.get("results"):
            return None

        r = data["results"][0]
        openfda = r.get("openfda", {})
        generic = openfda.get("generic_name", ["Not found"])[0]
        brand = openfda.get("brand_name", openfda.get("proprietary_name", ["Not found"]))[0]

        def get_section(key, limit=1200):
            val = r.get(key, ["Not available"])
            if isinstance(val, list) and val:
                return val[0][:limit]
            return "Not available"

        return {
            "generic": generic, "brand": brand,
            "drug_class": "Not structured in API — refer to full label.",
            "mechanism": "Refer to full label (not structured in API).",
            "spectrum": "Refer to full label (not structured in API).",
            "coverage": [],
            "indications": get_section("indications_and_usage"),
            "side_effects": get_section("adverse_reactions"),
            "pregnancy": "Refer to full label.",
            "cross_allergy": "Refer to full label.",
            "bioavailability": "Refer to full label.",
            "max_duration": "Refer to full label (not structured).",
            "dosing_adults": get_section("dosage_and_administration", 500),
            "dosing_peds": "Refer to full label.",
            "dosing_renal": "Refer to full label.",
            "pharmacist_notes": "📋 Pulled live from the FDA label API — verify against full prescribing information.",
            "source": "🌐 Online FDA",
        }
    except requests.RequestException:
        return None


def get_curated(key):
    """Curated lookup ONLY — never silently swapped for online data."""
    if key not in ANTIMICROBIALS:
        return None
    data = ANTIMICROBIALS[key].copy()
    data["source"] = "⚡ Curated Local DB"
    return data


def pcn_cross_reactivity_banner(data):
    if not st.session_state.pcn_allergy:
        return
    drug_class = data.get("drug_class", "")
    if drug_class in BETA_LACTAM_CLASSES:
        st.error("🚨 **Same penicillin-class beta-lactam ring — avoid** in patients with a history of PCN anaphylaxis.")
    elif drug_class in CEPHALOSPORIN_CLASSES:
        st.warning("⚠️ **Cephalosporin** — low (~1-5%) cross-reactivity with penicillins. Avoid if the PCN reaction was anaphylaxis; use caution otherwise.")
    elif "cross-react" in data.get("cross_allergy", "").lower() and "no cross" not in data.get("cross_allergy", "").lower():
        st.warning(f"⚠️ Cross-allergy note: {data['cross_allergy']}")
    else:
        st.success("✅ No significant cross-reactivity with penicillins expected for this agent (verify against the patient's specific reaction history).")


def quick_facts_row(data):
    mech = data.get("mechanism", "").lower()
    if "bactericidal" in mech:
        activity = badge("Bactericidal", "green")
    elif "bacteriostatic" in mech:
        activity = badge("Bacteriostatic", "yellow")
    else:
        activity = badge("Activity: see label", "grey")

    renal_text = data.get("dosing_renal", "")
    if "no adjustment" in renal_text.lower():
        renal = badge("Renal adj: not required", "green")
    elif renal_text and renal_text != "Refer to full label.":
        renal = badge("Renal adj: required", "red")
    else:
        renal = badge("Renal adj: see label", "grey")

    preg = data.get("pregnancy", "")
    preg_match = re.search(r"Category\s+([A-DX])", preg)
    if preg_match:
        cat = preg_match.group(1)
        tone = {"A": "green", "B": "green", "C": "yellow", "D": "red", "X": "red"}.get(cat, "grey")
        pregnancy = badge(f"Pregnancy: Category {cat}", tone)
    else:
        pregnancy = badge("Pregnancy: see label", "grey")

    drug_class = data.get("drug_class", "")
    if drug_class in BETA_LACTAM_CLASSES:
        allergy = badge("Beta-lactam (PCN class)", "red")
    elif drug_class in CEPHALOSPORIN_CLASSES:
        allergy = badge("Cephalosporin (~5% PCN cross-rx)", "yellow")
    else:
        allergy = badge("No PCN cross-reactivity", "green")

    st.markdown(activity + renal + pregnancy + allergy, unsafe_allow_html=True)


def build_summary_text(key, data):
    lines = [f"{data['generic']} ({data['brand']})", "=" * 40, f"Source: {data.get('source', 'N/A')}", ""]
    for field, label in FIELD_LABELS:
        lines.append(f"{label}: {data.get(field, 'N/A')}")
    lines.append("")
    lines.append("Generated by the Antimicrobial Prescribing Reference tool.")
    lines.append("Verify against institutional protocols and full prescribing information before clinical use.")
    return "\n".join(lines)


def render_drug_detail(key, data, key_prefix=""):
    display_name = f"{data['generic']} ({data['brand']})"
    st.caption(f"📌 Data Source: {data['source']}")
    quick_facts_row(data)
    pcn_cross_reactivity_banner(data)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Generic Name", data["generic"])
    with col2:
        st.metric("Brand Name", data["brand"])

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🦠 Micro & Indications", "💉 Dosing & PK", "⚠️ Side Effects & Safety",
        "🤰 Pregnancy & Allergy", "🧪 Pharmacist Notes",
    ])

    with tab1:
        st.subheader("⚙️ Mechanism of Action")
        st.info(data.get("mechanism", "N/A"))
        st.subheader("🎯 Spectrum of Activity")
        st.success(data.get("spectrum", "N/A"))
        st.subheader("🩺 Indications")
        st.write(data.get("indications", "N/A"))
        st.subheader("⏳ Max Treatment Duration")
        st.info(data.get("max_duration", "N/A"))

    with tab2:
        st.subheader("👨 Adults")
        st.code(data.get("dosing_adults", "N/A"))
        st.subheader("🧒 Pediatrics")
        st.code(data.get("dosing_peds", "N/A"))
        st.subheader("🫘 Renal/Hepatic Adjustment")
        st.code(data.get("dosing_renal", "N/A"))
        with st.expander("🧮 Estimate CrCl (Cockcroft-Gault) to help interpret the adjustment above"):
            render_crcl_calculator(key_prefix=key_prefix + "_tab2")
        st.divider()
        st.subheader("📊 Pharmacokinetics")
        st.metric("Bioavailability", data.get("bioavailability", "N/A"))

    with tab3:
        st.subheader("⚠️ Adverse Reactions (Common & Serious)")
        st.warning(data.get("side_effects", "N/A"))
        st.caption("📌 Note: This is not exhaustive. Refer to full label.")

    with tab4:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🤰 Pregnancy Category")
            st.info(data.get("pregnancy", "N/A"))
        with col_b:
            st.subheader("🔄 Cross-Allergy Risk")
            st.info(data.get("cross_allergy", "N/A"))

    with tab5:
        st.subheader("📦 Important Notes for Pharmacy & Administration")
        st.error(data.get("pharmacist_notes", "N/A"))
        if data["source"] == "🌐 Online FDA":
            st.caption("⚠️ This drug was pulled from the FDA label. Some structured fields may be missing.")

    st.download_button(
        "⬇️ Download summary (.txt)",
        data=build_summary_text(key, data),
        file_name=f"{data['generic'].replace(' ', '_')}_summary.txt",
        mime="text/plain",
        key=f"{key_prefix}_download_{key}",
    )


def render_crcl_calculator(key_prefix=""):
    c1, c2, c3, c4 = st.columns(4)
    age = c1.number_input("Age (yrs)", min_value=0, max_value=120, value=65, key=f"{key_prefix}_age")
    weight = c2.number_input("Weight (kg)", min_value=0.0, value=70.0, step=1.0, key=f"{key_prefix}_wt")
    scr = c3.number_input("Serum Cr (mg/dL)", min_value=0.0, value=1.0, step=0.1, key=f"{key_prefix}_scr")
    sex = c4.selectbox("Sex", ["Male", "Female"], key=f"{key_prefix}_sex")
    crcl = cockcroft_gault(age, weight, scr, sex == "Female")
    if crcl is not None:
        st.metric("Estimated CrCl (Cockcroft-Gault)", f"{crcl:.0f} mL/min")
        st.caption("Cockcroft-Gault uses actual body weight here; consider ideal/adjusted body weight for obese patients per institutional policy.")


# ---------------------------------------------------------------------------
# SIDEBAR — controls (rendered before the main content depends on them)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.checkbox("⚠️ Patient has PCN anaphylaxis history", key="pcn_allergy")
    st.checkbox("🆚 Compare two drugs", key="compare_mode")

    st.divider()
    st.subheader("🔎 Filter the drug list")
    filter_classes = st.multiselect("Drug class", ALL_CLASSES, key="filter_classes")
    filter_coverage = st.multiselect("Organism coverage", ALL_COVERAGE, key="filter_coverage")

# ---------------------------------------------------------------------------
# FILTERED OPTION LIST
# ---------------------------------------------------------------------------
def matches_filters(key):
    d = ANTIMICROBIALS[key]
    if filter_classes and d["drug_class"] not in filter_classes:
        return False
    if filter_coverage and not any(tag in d["coverage"] for tag in filter_coverage):
        return False
    return True


filtered_keys = sorted([k for k in ANTIMICROBIALS if matches_filters(k)], key=label_for)

# ---------------------------------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------------------------------
st.title("🧫 Antimicrobial Prescribing Reference")
st.warning(
    "⚠️ **Clinical decision-support reference only.** Verify all dosing and clinical decisions "
    "against institutional protocols, your local antibiogram, and current full prescribing "
    "information before use in patient care."
)
st.caption("Search by generic or brand name. Use the sidebar to filter by drug class or organism coverage, flag a PCN allergy, or compare two agents side by side.")

if not filtered_keys:
    st.info("No curated drugs match the current filters — clear a filter in the sidebar.")
else:
    if st.session_state.compare_mode:
        st.subheader("🆚 Compare two drugs")
        c1, c2 = st.columns(2)
        with c1:
            key_a = st.selectbox("Drug A", filtered_keys, format_func=label_for, key="cmp_a")
        with c2:
            default_b_index = 1 if len(filtered_keys) > 1 else 0
            key_b = st.selectbox("Drug B", filtered_keys, format_func=label_for, index=default_b_index, key="cmp_b")

        data_a, data_b = get_curated(key_a), get_curated(key_b)
        remember_lookup(label_for(key_a))
        remember_lookup(label_for(key_b))
        st.divider()
        col_a, col_b = st.columns(2)
        for col, key, data in [(col_a, key_a, data_a), (col_b, key_b, data_b)]:
            with col:
                st.markdown(f"### {data['generic']} ({data['brand']})")
                quick_facts_row(data)
                pcn_cross_reactivity_banner(data)
                for field, label in FIELD_LABELS:
                    st.markdown(f"**{label}**")
                    st.write(data.get(field, "N/A"))
                    st.markdown("---")

    else:
        user_key = st.selectbox(
            "Search or select a drug",
            options=filtered_keys,
            format_func=label_for,
            index=None,
            placeholder="Type to search by generic or brand name... (e.g., Van, Cipro, Zosyn, Bactrim)",
            key="drug_select",
        )

        if user_key:
            data = get_curated(user_key)
            remember_lookup(label_for(user_key))
            st.divider()
            render_drug_detail(user_key, data, key_prefix="main")

    st.divider()
    with st.expander("🌐 Look up a drug that isn't in the curated list (live FDA label search)"):
        st.caption(
            "This queries the FDA's openFDA label API directly. Results are not curated or "
            "reviewed the way the drugs above are — always confirm against the full label."
        )
        free_text = st.text_input("Drug name (generic or brand)", placeholder="e.g., Augmentin, Levofloxacin")
        if st.button("Search FDA label") and free_text:
            resolved = BRAND_MAP.get(free_text.strip().lower(), free_text.strip().lower())
            if resolved in ANTIMICROBIALS:
                st.info(f"'{free_text}' is already in the curated list above as **{label_for(resolved)}** — use the dropdown for richer, reviewed data.")
            else:
                with st.spinner(f"Searching FDA online for '{free_text}'..."):
                    online_data = fetch_from_openfda(resolved)
                if online_data:
                    st.divider()
                    render_drug_detail(resolved, online_data, key_prefix="online")
                else:
                    st.error(f"❌ No FDA label data found for '{free_text}'.")

st.divider()
st.caption(
    f"Antimicrobial Prescribing Reference — curated content for teaching/reference purposes. "
    f"Not a substitute for clinical judgment, institutional guidelines, or an infectious "
    f"disease/antimicrobial stewardship consult. Session started {datetime.now():%Y-%m-%d}."
)

# ---------------------------------------------------------------------------
# SIDEBAR — recent lookups (rendered last so it reflects THIS run's activity,
# not the previous one; jumping via a history button actually navigates the
# main dropdown back to that drug, resetting filters/compare mode so it's
# guaranteed to be selectable).
# ---------------------------------------------------------------------------
with st.sidebar:
    st.divider()
    st.header("📜 Recent Lookups")
    if st.session_state.history:
        for drug in st.session_state.history:
            st.button(f"🔁 {drug}", key=f"hist_{drug}", on_click=jump_to_drug, args=(drug,))
    else:
        st.caption("No lookups yet this session.")
    st.divider()
    st.caption("🧫 Advanced Stewardship Tool")
