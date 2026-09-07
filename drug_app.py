import streamlit as st
import requests

st.set_page_config(page_title="Antimicrobial Stewardship", layout="wide")

# --- SESSION STATE ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- EXPANDED CLINICAL DATABASE WITH NEW FIELDS ---
ANTIMICROBIALS = {
    "amoxicillin": {
        "generic": "Amoxicillin", "brand": "Amoxil",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (penicillin class).",
        "spectrum": "✅ Gram-positive (Strep, Enterococcus). ✅ Limited Gram-negative (E. coli, H. influenzae). ❌ No anaerobes.",
        "indications": "Sinusitis, Otitis Media, Strep Pharyngitis, CAP, UTI, Dental prophylaxis.",
        "side_effects": "Diarrhea, nausea, rash. Risk of C. diff. Anaphylaxis in true PCN allergy.",
        "pregnancy": "Category B. Generally considered safe.",
        "cross_allergy": "⚠️ Cross-reacts with cephalosporins (low ~5-10%). Avoid if true anaphylaxis to PCN.",
        "bioavailability": "Oral: ~80%. Protein binding: ~20%.",
        "max_duration": "7-10 days (Uncomplicated UTI: 3-5 days).",
        "dosing_adults": "500 mg PO q8h OR 875 mg PO q12h.",
        "dosing_peds": "20-45 mg/kg/day PO divided q8-12h (Max 875 mg/dose).",
        "dosing_renal": "CrCl < 10 mL/min: Extend interval to q24h.",
        "pharmacist_notes": "✅ Can be crushed/split. Suspension must be refrigerated. Take with food to reduce GI upset."
    },
    "azithromycin": {
        "generic": "Azithromycin", "brand": "Zithromax",
        "mechanism": "Macrolide; binds 50S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Gram-positive (Strep, Staph). ✅ Atypicals (Chlamydia, Mycoplasma). ✅ Some Gram-negative (H. flu).",
        "indications": "CAP, AECB, Sinusitis, Strep (PCN-allergic), STIs (Chlamydia/Gonorrhea).",
        "side_effects": "Diarrhea, nausea, QT prolongation (dose-dependent), hepatotoxicity.",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~37%. Protein binding: ~50%.",
        "max_duration": "5-day Z-Pak OR 2g single dose for chlamydia.",
        "dosing_adults": "500mg day 1, then 250mg days 2-5. Or 2g single dose.",
        "dosing_peds": "10 mg/kg day 1, then 5 mg/kg days 2-5 (Max 500mg/250mg).",
        "dosing_renal": "No adjustment needed.",
        "pharmacist_notes": "✅ IV compatible with NS/D5W (infuse over 1 hr). Can take with food. Caution in known QT prolongation."
    },
    "ciprofloxacin": {
        "generic": "Ciprofloxacin", "brand": "Cipro",
        "mechanism": "Fluoroquinolone; inhibits DNA gyrase (topoisomerase II), bactericidal.",
        "spectrum": "✅ Strong Gram-negative (Pseudomonas, Enterobacter, E. coli). ⚠️ Moderate Gram-positive (Staph). ❌ No anaerobes.",
        "indications": "Complicated UTIs, Pyelonephritis, Prostatitis, Bone/Joint infections, Anthrax.",
        "side_effects": "⚠️ Tendon rupture (Achilles). Peripheral neuropathy. CNS agitation. QT prolongation.",
        "pregnancy": "Category C. Avoid in pregnancy/breastfeeding.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~70%. Protein binding: ~25%.",
        "max_duration": "UTI: 3-7 days. Prostatitis: 28 days. Osteomyelitis: 4-6 weeks.",
        "dosing_adults": "250-750 mg PO q12h. IV: 400 mg q12h.",
        "dosing_peds": "Only for specific indications: 10-20 mg/kg/dose PO q12h (Max 750 mg).",
        "dosing_renal": "CrCl 30-50: 250-500 mg q12h. CrCl <30: 250-500 mg q18-24h.",
        "pharmacist_notes": "🚫 Avoid in children <18 unless specific indication. ☕ Avoid dairy/antacids/iron/zinc within 2 hours. Hold dose 24h before/after IV contrast."
    },
    "doxycycline": {
        "generic": "Doxycycline", "brand": "Vibramycin",
        "mechanism": "Tetracycline; binds 30S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Atypicals (Chlamydia, Mycoplasma, Rickettsia). ✅ MRSA (some). ✅ Gram-negative (some).",
        "indications": "Skin/soft tissue infections, CAP (atypical), Lyme disease, RMSF, Malaria prophylaxis.",
        "side_effects": "Photosensitivity (sunburn risk), esophageal ulceration, tooth discoloration (if age <8).",
        "pregnancy": "Category D. Avoid (affects fetal bone/teeth).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >90%. Protein binding: ~90%.",
        "max_duration": "Lyme: 10-21 days. CAP: 7-10 days.",
        "dosing_adults": "100 mg PO/IV q12h (Loading: 200 mg day 1).",
        "dosing_peds": ">8 yrs: 2.2 mg/kg/dose q12h. <8 yrs: Avoid.",
        "dosing_renal": "No adjustment needed.",
        "pharmacist_notes": "☕ Swallow with full glass of water; remain upright for 30 min. Can take with food. 🚫 Avoid in children <8 and pregnant women."
    },
    "metronidazole": {
        "generic": "Metronidazole", "brand": "Flagyl",
        "mechanism": "Nitroimidazole; disrupts DNA and protein synthesis in anaerobes (bactericidal).",
        "spectrum": "✅ Excellent anaerobes (Bacteroides, Clostridium). ✅ Some protozoa (Trichomonas, Giardia). ❌ No aerobes.",
        "indications": "Intra-abdominal infections, C. difficile, Bacterial vaginosis, Trichomoniasis.",
        "side_effects": "Metallic taste, nausea, peripheral neuropathy (long-term), disulfiram-like reaction with alcohol.",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >95%. Protein binding: <20%.",
        "max_duration": "C. diff: 10-14 days. Intra-abdominal: 7-10 days.",
        "dosing_adults": "500 mg PO q8h (or 250 mg q6h). IV: 500 mg q6-8h.",
        "dosing_peds": "7.5 mg/kg/dose PO/IV q6h (Max 500 mg).",
        "dosing_renal": "CrCl <10: Half dose (IV only, no adjustment for PO).",
        "pharmacist_notes": "🚫 ABSOLUTELY NO ALCOHOL during therapy and 48 hrs after (disulfiram). ☕ Take with food."
    },
    "vancomycin": {
        "generic": "Vancomycin", "brand": "Vancocin",
        "mechanism": "Glycopeptide; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ MRSA (strong). ✅ Gram-positive (Strep, Enterococcus). ❌ No Gram-negative.",
        "indications": "MRSA infections, C. difficile (PO only), Endocarditis, Meningitis.",
        "side_effects": "Nephrotoxicity, Ototoxicity, Red Man Syndrome (rapid IV), thrombophlebitis.",
        "pregnancy": "Category C. Use if clearly needed (monitor levels).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: 0% (PO only for C. diff). IV: 100%. Protein binding: ~55%.",
        "max_duration": "MRSA bacteremia: 14 days minimum. C. diff: 10 days.",
        "dosing_adults": "PO: 125-500 mg q6h. IV: 15-20 mg/kg q8-12h (AUC-guided preferred).",
        "dosing_peds": "IV: 10-15 mg/kg/dose q6h. PO: 10 mg/kg/dose q6h (Max 125 mg for C. diff).",
        "dosing_renal": "Extend interval based on CrCl (e.g., q24-48h for severe renal impairment).",
        "pharmacist_notes": "🚨 IV must be infused over ≥60 min (prevents Red Man). 🩸 Monitor trough levels (10-20 mg/L for MRSA) or AUC. PO route is ONLY for C. difficile."
    },
    "ceftriaxone": {
        "generic": "Ceftriaxone", "brand": "Rocephin",
        "mechanism": "3rd generation cephalosporin; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Broad Gram-negative (Neisseria, E. coli, Klebsiella). ✅ Moderate Gram-positive (Strep). ❌ No anaerobes.",
        "indications": "CAP, Gonorrhea, Intra-abdominal, Meningitis, Lyme (neuro).",
        "side_effects": "Diarrhea, biliary sludge (especially children), C. diff risk. Eosinophilia.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Caution in severe PCN allergy (cross-reactivity ~5%). Avoid if anaphylaxis.",
        "bioavailability": "IV/IM only. Protein binding: ~95%.",
        "max_duration": "CAP: 7-10 days. Meningitis: 14-21 days. Gonorrhea: Single dose.",
        "dosing_adults": "1-2 g IV/IM q24h (Gonorrhea: 500mg IM single dose).",
        "dosing_peds": "50-75 mg/kg IV/IM q24h (Max 2g). Meningitis: 80-100 mg/kg q12-24h.",
        "dosing_renal": "No adjustment needed (biliary excretion).",
        "pharmacist_notes": "✅ IM can be mixed with Lidocaine for pain. 🚫 Do NOT mix with Calcium-containing IV solutions (precipitate in neonates)."
    },
    "gentamicin": {
        "generic": "Gentamicin", "brand": "Generic",
        "mechanism": "Aminoglycoside; binds 30S ribosome, inhibits protein synthesis (bactericidal, concentration-dependent).",
        "spectrum": "✅ Strong Gram-negative (Pseudomonas, E. coli, Enterobacter). ✅ Synergy with beta-lactams for Enterococcus. ❌ No anaerobes.",
        "indications": "Gram-negative sepsis, UTI, Endocarditis (synergy), Neutropenic fever.",
        "side_effects": "Nephrotoxicity (ATN), Ototoxicity (vestibular/cochlear), Neuromuscular blockade.",
        "pregnancy": "Category D. Avoid unless life-saving.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV/IM only. Protein binding: <10%.",
        "max_duration": "7-14 days (prolonged use increases toxicity risk).",
        "dosing_adults": "Traditional: 1-1.7 mg/kg IV/IM q8h. Extended: 5-7 mg/kg IV q24h.",
        "dosing_peds": "2.5 mg/kg IV q8h (Neonates: 2.5 mg/kg q12h).",
        "dosing_renal": "⛔ CRITICAL adjustment. Extend interval based on CrCl (e.g., q12h if CrCl 30-70, q24-48h if <30).",
        "pharmacist_notes": "🩸 Mandatory trough (<1-2 mg/L) and peak (5-10 mg/L) monitoring. Monitor BUN/Cr q2-3 days. Infuse over 30-60 min. Avoid loop diuretics."
    },
    "piperacillin_tazobactam": {
        "generic": "Piperacillin-Tazobactam", "brand": "Zosyn",
        "mechanism": "Penicillin + beta-lactamase inhibitor; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Broad: Gram-positive, Gram-negative (including Pseudomonas), and Anaerobes (Bacteroides).",
        "indications": "Severe intra-abdominal, skin, pneumonia. Empiric coverage for Pseudomonas.",
        "side_effects": "Diarrhea, headache, thrombocytopenia, neutropenia. Bleeding risk (platelet dysfunction).",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Penicillin-class. Avoid if severe PCN anaphylaxis.",
        "bioavailability": "IV only. Protein binding: ~30%.",
        "max_duration": "7-14 days based on cultures.",
        "dosing_adults": "3.375 g IV q6h OR 4.5 g IV q8h (Extended infusion preferred for Pseudomonas).",
        "dosing_peds": "80-100 mg/kg/dose IV q6-8h (piperacillin component).",
        "dosing_renal": "CrCl 20-40: 2.25 g IV q6h. CrCl <20: 2.25 g IV q8h.",
        "pharmacist_notes": "✅ Extended infusion (4.5g over 4 hrs) recommended for severe Pseudomonas. ⚠️ Contains Sodium (~2.5 mEq/g) - monitor in CHF."
    },
    "clindamycin": {
        "generic": "Clindamycin", "brand": "Cleocin",
        "mechanism": "Lincosamide; binds 50S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Gram-positive (Strep, Staph, including some MRSA). ✅ Excellent anaerobes (Bacteroides, Clostridium). ❌ No Gram-negative.",
        "indications": "Skin/soft tissue infections (MRSA), aspiration pneumonia, dental infections, anaerobic infections.",
        "side_effects": "⚠️ High risk of C. difficile infection (~10-20%). Diarrhea, rash, hepatotoxicity.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~90%. Protein binding: ~90%.",
        "max_duration": "7-10 days (prolonged use increases C. diff risk).",
        "dosing_adults": "300-450 mg PO q6-8h. IV: 600-900 mg q8h.",
        "dosing_peds": "10-20 mg/kg/dose PO/IV q6-8h (Max 600 mg/dose).",
        "dosing_renal": "No adjustment needed.",
        "pharmacist_notes": "✅ IV compatible with NS/D5W (infuse over 10-60 min). 🚨 Be highly vigilant for C. diff diarrhea. Can cause esophagitis if not swallowed with water."
    }
}

# --- BRAND MAPPING (UPDATED WITH NEW DRUGS) ---
BRAND_MAP = {
    "zithromax": "azithromycin", "cipro": "ciprofloxacin", "flagyl": "metronidazole",
    "vancocin": "vancomycin", "rocephin": "ceftriaxone", "zosyn": "piperacillin_tazobactam",
    "vibramycin": "doxycycline", "amoxil": "amoxicillin", "cleocin": "clindamycin",
    "bactrim": "sulfamethoxazole-trimethoprim", "zyvox": "linezolid"
}


# --- ONLINE FDA FETCHER ---
def fetch_from_openfda(search_term):
    clean_term = search_term.strip().lower()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    query = f'openfda.generic_name:"{clean_term}"'
    url = "https://api.fda.gov/drug/label.json"

    try:
        response = requests.get(url, params={"search": query, "limit": 1}, headers=headers, timeout=10)
        if response.status_code == 403:
            alt_response = requests.get(
                f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:{clean_term}&limit=1",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if alt_response.status_code != 200:
                return None
            data = alt_response.json()
        elif response.status_code != 200:
            return None
        else:
            data = response.json()

        if not data.get("results"):
            return None

        r = data["results"][0]
        openfda = r.get("openfda", {})

        generic = openfda.get("generic_name", ["Not found"])[0]
        brand = openfda.get("brand_name", ["Not found"])[0]
        if brand == "Not found" and openfda.get("proprietary_name"):
            brand = openfda.get("proprietary_name", ["Not found"])[0]

        def get_section(key):
            val = r.get(key, ["Not available"])
            if isinstance(val, list) and val:
                return val[0][:1200]
            return "Not available"

        return {
            "generic": generic, "brand": brand,
            "mechanism": "Refer to full label (not structured in API).",
            "spectrum": "Check full label for spectrum.",
            "indications": get_section("indications_and_usage"),
            "side_effects": get_section("adverse_reactions"),
            "pregnancy": "Check full label.",
            "cross_allergy": "Check full label.",
            "bioavailability": "Check full label.",
            "max_duration": "Check label. Not structured.",
            "dosing_adults": get_section("dosage_and_administration")[:500],
            "dosing_peds": "Refer to label.",
            "dosing_renal": "Refer to label.",
            "pharmacist_notes": "📋 FDA label data. Verify with full prescribing info.",
            "source": "🌐 Online FDA"
        }
    except:
        return None


# --- MAIN SEARCH ---
def get_drug_info(user_input):
    clean = user_input.strip().lower()
    search_key = BRAND_MAP.get(clean, clean)

    if search_key in ANTIMICROBIALS:
        data = ANTIMICROBIALS[search_key].copy()
        data["source"] = "⚡ Curated Local DB"
        return data

    with st.spinner(f"Searching FDA online for '{user_input}'..."):
        online = fetch_from_openfda(search_key)
        if online:
            online["source"] = "🌐 Online FDA"
            return online
    return None


# --- SIDEBAR ---
with st.sidebar:
    st.header("📜 Recent Lookups")
    if st.session_state.history:
        for drug in st.session_state.history:
            if st.button(f"🔁 {drug}"):
                st.session_state.selected_drug = drug
                st.rerun()
    st.divider()
    st.caption("🧫 Advanced Stewardship Tool")

# --- MAIN PAGE ---
st.title("🧫 Antimicrobial Prescribing Reference")
st.caption("Search by generic or brand (e.g., Vancomycin, Zosyn, Bactrim, Cleocin)")

#user_input = st.text_input("Enter Antimicrobial Name:", placeholder="e.g., Vancomycin, Bactrim, Clindamycin").strip()
#create searchable dropdown with all drugs
all_options = sorted(list(ANTIMICROBIALS.keys()))
user_input = st.selectbox(
    "search or select a drug",
    options=all_options,
    index=None, #No default selection
    placeholder="Type to search... (e.g., Van, Cipro, Zosyn)"
)
if user_input:
    data= get_drug_info(user_input)
#if user_input:
 #   data = get_drug_info(user_input)

    if data:
        display_name = user_input.capitalize()
        if display_name in st.session_state.history:
            st.session_state.history.remove(display_name)
        st.session_state.history.insert(0, display_name)
        st.session_state.history = st.session_state.history[:5]

        st.divider()
        st.caption(f"📌 Data Source: {data['source']}")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Generic Name", data["generic"])
        with col2:
            st.metric("Brand Name", data["brand"])

        # --- 5 NEW INFORMATIVE TABS ---
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🦠 Micro & Indications",
            "💉 Dosing & PK",
            "⚠️ Side Effects & Safety",
            "🤰 Pregnancy & Allergy",
            "🧪 Pharmacist Notes"
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
            if data['source'] == "🌐 Online FDA":
                st.caption("⚠️ This drug was pulled from the FDA label. Some structured fields may be missing.")

    else:
        st.error(f"❌ No data found for '{user_input}'. Try generic names like Amoxicillin, Vancomycin, or Bactrim.")