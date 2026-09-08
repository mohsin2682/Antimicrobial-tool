import re
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Antimicrobial Stewardship App", layout="wide", page_icon="🧫")

# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = []
if "pcn_allergy" not in st.session_state:
    st.session_state.pcn_allergy = False
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "🔍 Drug Lookup"

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
        "aware": "Access",
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
        "aware": "Watch",
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
        "aware": "Watch",
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
        "aware": "Access",
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
        "aware": "Access",
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
        "aware": "Watch",
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
        "aware": "Watch",
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
        "aware": "Access",
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
        "aware": "Watch",
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
        "aware": "Access",
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
        "aware": "Access",
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
        "aware": "Reserve",
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
    "penicillin_vk": {
        "generic": "Penicillin V", "brand": "Pen-Vee K",
        "drug_class": "Natural penicillin",
        "aware": "Access",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (narrow-spectrum penicillin, bactericidal).",
        "spectrum": "✅ Strep species (excellent). ✅ Oral anaerobes. ❌ No Staph (penicillinase), no Gram-negative.",
        "coverage": ["Gram-positive", "Anaerobes (oral)"],
        "indications": "Strep pharyngitis, rheumatic fever prophylaxis, dental infections, mild skin infections.",
        "side_effects": "Diarrhea, nausea, rash. Anaphylaxis in true PCN allergy (highest-risk beta-lactam for skin testing reference).",
        "pregnancy": "Category B. Considered safe.",
        "cross_allergy": "⚠️ The reference penicillin — defines \"PCN allergy.\" Cross-reacts with other penicillins; low cross-reactivity with cephalosporins.",
        "bioavailability": "Oral: ~60-70% (food reduces absorption). Protein binding: ~80%.",
        "max_duration": "Strep pharyngitis: 10 days. RF prophylaxis: years (often through age 21+).",
        "dosing_adults": "250-500 mg PO q6h.",
        "dosing_peds": "25-50 mg/kg/day PO divided q6-8h (Max per adult dosing).",
        "dosing_renal": "CrCl <10: Extend interval to q8h.",
        "pharmacist_notes": "☕ Take on empty stomach (1h before/2h after meals) for best absorption. ✅ First-line, narrow-spectrum choice for strep pharyngitis per IDSA — favor over broader agents when susceptible.",
    },
    "ampicillin_sulbactam": {
        "generic": "Ampicillin-Sulbactam", "brand": "Unasyn",
        "drug_class": "Beta-lactam/Beta-lactamase inhibitor",
        "aware": "Access",
        "mechanism": "Aminopenicillin + beta-lactamase inhibitor; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive. ✅ Gram-negative (beta-lactamase producing H. flu, some E. coli). ✅ Oral/intra-abdominal anaerobes. ❌ No Pseudomonas.",
        "coverage": ["Gram-positive", "Gram-negative (limited)", "Anaerobes"],
        "indications": "Aspiration pneumonia, intra-abdominal infections, diabetic foot infections, human/animal bites, pelvic infections.",
        "side_effects": "Diarrhea, rash, C. diff risk.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Penicillin-class. Avoid if severe PCN anaphylaxis.",
        "bioavailability": "IV/IM only. Protein binding: ~28-38%.",
        "max_duration": "5-14 days depending on source control.",
        "dosing_adults": "1.5-3 g IV q6h (max 4 g/day of sulbactam component).",
        "dosing_peds": "100-200 mg/kg/day (ampicillin component) IV divided q6h.",
        "dosing_renal": "CrCl 15-29: 1.5-3 g q12h. CrCl 5-14: 1.5-3 g q24h.",
        "pharmacist_notes": "✅ A go-to Access-category choice for aspiration/bite-wound coverage before reaching for broader Watch-category agents like Zosyn.",
    },
    "amoxicillin_clavulanate": {
        "generic": "Amoxicillin-Clavulanate", "brand": "Augmentin",
        "drug_class": "Beta-lactam/Beta-lactamase inhibitor",
        "aware": "Access",
        "mechanism": "Aminopenicillin + beta-lactamase inhibitor (clavulanic acid); inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive. ✅ Gram-negative (beta-lactamase-producing H. flu, Moraxella). ✅ Oral anaerobes. ❌ No Pseudomonas.",
        "coverage": ["Gram-positive", "Gram-negative (limited)", "Anaerobes"],
        "indications": "Sinusitis, otitis media (beta-lactamase-producing organisms), animal/human bites, diabetic foot infections, CAP.",
        "side_effects": "Diarrhea (more than amoxicillin alone, due to clavulanate), nausea, rash, rare cholestatic hepatitis.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Penicillin-class. Cross-reacts with cephalosporins (low ~5-10%).",
        "bioavailability": "Oral: ~80% (amoxicillin component). Protein binding: ~20%/~25%.",
        "max_duration": "5-10 days depending on indication.",
        "dosing_adults": "875/125 mg PO q12h OR 500/125 mg PO q8h.",
        "dosing_peds": "45-90 mg/kg/day (amoxicillin component) PO divided q12h.",
        "dosing_renal": "CrCl 10-30: 500/125 mg q12h. CrCl <10: 500/125 mg q24h.",
        "pharmacist_notes": "☕ Take with food to reduce GI upset. ✅ Use the formulation with the lowest clavulanate ratio available (e.g., 875/125 over 500/125 dosed more frequently) to limit diarrhea.",
    },
    "cephalexin": {
        "generic": "Cephalexin", "brand": "Keflex",
        "drug_class": "Cephalosporin (1st gen)",
        "aware": "Access",
        "mechanism": "1st generation cephalosporin; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive (Strep, MSSA). ✅ Limited Gram-negative (E. coli, Klebsiella, Proteus). ❌ No MRSA, no Pseudomonas, no anaerobes.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "Uncomplicated skin/soft tissue infections (non-MRSA), uncomplicated cystitis, strep pharyngitis (PCN-allergic, non-anaphylactic).",
        "side_effects": "Diarrhea, nausea, rash. C. diff risk (lower than broader cephalosporins).",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (~1-5%, low). Avoid if severe PCN anaphylaxis.",
        "bioavailability": "Oral: ~90%. Protein binding: ~10-15%.",
        "max_duration": "5-7 days (skin/soft tissue); 3-7 days (UTI).",
        "dosing_adults": "250-500 mg PO q6h (or 500 mg q12h for skin infections).",
        "dosing_peds": "25-50 mg/kg/day PO divided q6-8h (Max 4 g/day).",
        "dosing_renal": "CrCl 10-30: q8-12h. CrCl <10: q12-24h.",
        "pharmacist_notes": "✅ First-line, narrow oral option for uncomplicated non-MRSA skin infections — add doxycycline/TMP-SMX/clindamycin instead (not on top of) if MRSA is a concern.",
    },
    "cefazolin": {
        "generic": "Cefazolin", "brand": "Ancef",
        "drug_class": "Cephalosporin (1st gen)",
        "aware": "Access",
        "mechanism": "1st generation cephalosporin; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive (Strep, MSSA — drug of choice for MSSA bacteremia). ✅ Limited Gram-negative. ❌ No MRSA, no Pseudomonas.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "Surgical prophylaxis (workhorse agent), MSSA bacteremia/endocarditis, uncomplicated cellulitis.",
        "side_effects": "Diarrhea, rash, phlebitis at infusion site.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (~1-5%, low). Often tolerated even with non-anaphylactic PCN allergy.",
        "bioavailability": "IV/IM only. Protein binding: ~75-85%.",
        "max_duration": "Surgical ppx: single pre-op dose (± redose intraop). MSSA bacteremia: 2+ weeks per source.",
        "dosing_adults": "1-2 g IV q8h (Surgical prophylaxis: 2 g IV within 60 min pre-incision, redose q4h intraop).",
        "dosing_peds": "50-100 mg/kg/day IV divided q8h (Max 6 g/day).",
        "dosing_renal": "CrCl 35-54: no change usually. CrCl 11-34: q12h. CrCl <10: q18-24h.",
        "pharmacist_notes": "✅ Preferred agent for MSSA bacteremia over vancomycin when the organism is susceptible — better outcomes data. The default surgical prophylaxis cephalosporin.",
    },
    "cefepime": {
        "generic": "Cefepime", "brand": "Maxipime",
        "drug_class": "Cephalosporin (4th gen)",
        "aware": "Watch",
        "mechanism": "4th generation cephalosporin; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Broad Gram-negative including Pseudomonas. ✅ Gram-positive (Strep, MSSA). ❌ No MRSA, no anaerobes, no Enterococcus.",
        "coverage": ["Gram-negative", "Pseudomonas", "Gram-positive (moderate)"],
        "indications": "Febrile neutropenia, healthcare-associated/hospital-acquired pneumonia, complicated UTI, empiric Pseudomonas coverage.",
        "side_effects": "⚠️ Neurotoxicity (encephalopathy, myoclonus, seizures) — especially with renal impairment/inadequate dose reduction. Diarrhea, rash.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (~1-5%, low). Avoid if severe PCN anaphylaxis.",
        "bioavailability": "IV/IM only. Protein binding: ~20%.",
        "max_duration": "7-14 days depending on source; febrile neutropenia per ANC recovery.",
        "dosing_adults": "1-2 g IV q8-12h (higher dose/frequency for Pseudomonas or CNS infection).",
        "dosing_peds": "50 mg/kg/dose IV q8-12h (Max 2 g/dose).",
        "dosing_renal": "⛔ CRITICAL — neurotoxicity risk if not adjusted. CrCl 30-60: 2 g q12h. CrCl 11-29: 2 g q24h. CrCl <11: 1 g q24h.",
        "pharmacist_notes": "🚨 Renally adjust promptly and monitor mental status — cefepime neurotoxicity is under-recognized and often mistaken for other causes of delirium in the renally impaired.",
    },
    "ceftazidime": {
        "generic": "Ceftazidime", "brand": "Fortaz",
        "drug_class": "Cephalosporin (3rd gen, antipseudomonal)",
        "aware": "Watch",
        "mechanism": "3rd generation cephalosporin with antipseudomonal activity; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Strong Gram-negative including Pseudomonas. ⚠️ Weak Gram-positive (poor Strep/Staph coverage). ❌ No anaerobes.",
        "coverage": ["Gram-negative", "Pseudomonas"],
        "indications": "Pseudomonas infections, hospital-acquired pneumonia, complicated UTI/intra-abdominal (with anaerobic coverage added), febrile neutropenia.",
        "side_effects": "Diarrhea, rash, eosinophilia. Neurotoxicity at high doses with renal impairment.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (~1-5%, low). Avoid if severe PCN anaphylaxis.",
        "bioavailability": "IV/IM only. Protein binding: ~10%.",
        "max_duration": "7-14 days depending on source.",
        "dosing_adults": "1-2 g IV q8h.",
        "dosing_peds": "30-50 mg/kg/dose IV q8h (Max 6 g/day).",
        "dosing_renal": "CrCl 31-50: q12h. CrCl 16-30: q24h. CrCl <15: q24-48h.",
        "pharmacist_notes": "⚠️ Poor Gram-positive coverage — add MRSA/Strep coverage separately when needed. Reserve for confirmed/suspected Pseudomonas rather than routine empiric use.",
    },
    "meropenem": {
        "generic": "Meropenem", "brand": "Merrem",
        "drug_class": "Carbapenem",
        "aware": "Watch",
        "mechanism": "Carbapenem; inhibits cell wall synthesis (bactericidal, very broad spectrum).",
        "spectrum": "✅ Broad Gram-positive, Gram-negative (including Pseudomonas, ESBL producers), and Anaerobes. ❌ No MRSA, no VRE, no atypicals.",
        "coverage": ["Gram-positive", "Gram-negative", "Pseudomonas", "Anaerobes"],
        "indications": "Severe/polymicrobial infections, ESBL-producing organism infections, meningitis, febrile neutropenia (broad empiric coverage).",
        "side_effects": "Diarrhea, rash, seizures (higher risk than other carbapenems, especially with renal impairment/high dose), C. diff risk.",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "Low cross-reactivity with penicillins (~1%); generally tolerated even in PCN allergy, but caution if anaphylaxis history.",
        "bioavailability": "IV only. Protein binding: ~2%.",
        "max_duration": "7-14 days depending on source; meningitis up to 21 days.",
        "dosing_adults": "1 g IV q8h (Meningitis/CNS: 2 g IV q8h).",
        "dosing_peds": "20 mg/kg/dose IV q8h (Meningitis: 40 mg/kg/dose q8h, Max 2 g/dose).",
        "dosing_renal": "CrCl 26-50: 1 g q12h. CrCl 10-25: 500 mg q12h. CrCl <10: 500 mg q24h.",
        "pharmacist_notes": "🚨 A \"Watch\"-category carbapenem — reserve for ESBL/polymicrobial/severe infections rather than routine empiric broad coverage; involve stewardship/ID for prolonged use. Extended infusion improves target attainment in critical illness.",
    },
    "ertapenem": {
        "generic": "Ertapenem", "brand": "Invanz",
        "drug_class": "Carbapenem",
        "aware": "Watch",
        "mechanism": "Carbapenem; inhibits cell wall synthesis (bactericidal). Unlike other carbapenems, no reliable Pseudomonas or Enterococcus activity.",
        "spectrum": "✅ Broad Gram-positive, Gram-negative (including ESBL producers), and Anaerobes. ❌ No Pseudomonas, no Enterococcus, no MRSA.",
        "coverage": ["Gram-positive", "Gram-negative", "Anaerobes"],
        "indications": "Complicated intra-abdominal/skin infections, diabetic foot infections, ESBL-producing organism infections — favored for outpatient IV therapy given once-daily dosing.",
        "side_effects": "Diarrhea, phlebitis (IM associated with pain — often mixed with lidocaine), C. diff risk, seizures (less than meropenem/imipenem).",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "Low cross-reactivity with penicillins; generally tolerated even in PCN allergy, but caution if anaphylaxis history.",
        "bioavailability": "IV/IM only. Protein binding: ~85-95% (concentration-dependent).",
        "max_duration": "7-14 days depending on source.",
        "dosing_adults": "1 g IV/IM once daily.",
        "dosing_peds": "15 mg/kg/dose IV q12h (Max 1 g/day), ages 3 months-12 years.",
        "dosing_renal": "CrCl ≤30: 500 mg IV/IM once daily.",
        "pharmacist_notes": "✅ Once-daily dosing makes it a common OPAT (outpatient parenteral antibiotic therapy) choice. 🚫 No Pseudomonas coverage — don't substitute for meropenem/piperacillin-tazobactam when Pseudomonas is a concern.",
    },
    "levofloxacin": {
        "generic": "Levofloxacin", "brand": "Levaquin",
        "drug_class": "Fluoroquinolone",
        "aware": "Watch",
        "mechanism": "Fluoroquinolone; inhibits DNA gyrase/topoisomerase IV, bactericidal.",
        "spectrum": "✅ Gram-negative (including Pseudomonas at higher dose). ✅ Gram-positive (better Strep pneumoniae coverage than ciprofloxacin — a \"respiratory\" fluoroquinolone). ✅ Atypicals.",
        "coverage": ["Gram-negative", "Pseudomonas", "Gram-positive (moderate)", "Atypicals"],
        "indications": "CAP, complicated UTI/pyelonephritis, healthcare-associated pneumonia, TB (second-line).",
        "side_effects": "⚠️ Tendon rupture, peripheral neuropathy, CNS effects, QT prolongation. Same class warnings as ciprofloxacin.",
        "pregnancy": "Category C. Avoid in pregnancy/breastfeeding.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~99% (near-complete — IV and PO doses are equivalent).",
        "max_duration": "CAP: 5 days. Pyelonephritis: 5-7 days.",
        "dosing_adults": "500-750 mg PO/IV q24h.",
        "dosing_peds": "Only for specific indications; not first-line in children (arthropathy risk).",
        "dosing_renal": "CrCl 20-49: 500-750 mg first dose, then q48h. CrCl 10-19: 500-750 mg first dose, then q48h at reduced dose.",
        "pharmacist_notes": "✅ Near-100% oral bioavailability — IV-to-PO switch is essentially dose-equivalent. ☕ Avoid dairy/antacids/iron/zinc within 2 hours, same as ciprofloxacin.",
    },
    "nitrofurantoin": {
        "generic": "Nitrofurantoin", "brand": "Macrobid",
        "drug_class": "Nitrofuran",
        "aware": "Access",
        "mechanism": "Nitrofuran; damages bacterial DNA/ribosomal proteins via reactive intermediates (bactericidal at urinary concentrations).",
        "spectrum": "✅ E. coli (excellent, including many resistant strains). ✅ Enterococcus. ❌ Proteus, Pseudomonas (intrinsically resistant). Only concentrates in urine — no systemic use.",
        "coverage": ["Gram-negative (urinary)", "Gram-positive"],
        "indications": "Uncomplicated cystitis (first-line per IDSA), UTI prophylaxis (recurrent UTI).",
        "side_effects": "Nausea, pulmonary toxicity (acute/chronic, with prolonged use), hepatotoxicity (rare), peripheral neuropathy, hemolysis in G6PD deficiency.",
        "pregnancy": "Category B (avoid at term, 38-42 weeks — neonatal hemolysis risk).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~90% (macrocrystal form slows absorption, reduces GI upset). Protein binding: ~60%.",
        "max_duration": "Uncomplicated cystitis: 5 days (Macrobid). Prophylaxis: 50-100 mg qhs, long-term.",
        "dosing_adults": "100 mg PO q12h (Macrobid, macrocrystal). Prophylaxis: 50-100 mg qhs.",
        "dosing_peds": ">1 month: 5-7 mg/kg/day PO divided q6h (Max 400 mg/day).",
        "dosing_renal": "🚫 Avoid if CrCl <30 mL/min (or <60 mL/min per some stewardship guidance in older adults) — subtherapeutic urine levels + systemic accumulation/toxicity risk.",
        "pharmacist_notes": "✅ First-line Access-category agent for uncomplicated cystitis — preferred over fluoroquinolones/broader agents per IDSA guidance. 🚫 Not effective for pyelonephritis or systemic infection (doesn't reach therapeutic tissue/blood levels).",
    },
    "daptomycin": {
        "generic": "Daptomycin", "brand": "Cubicin",
        "drug_class": "Lipopeptide",
        "aware": "Reserve",
        "mechanism": "Cyclic lipopeptide; binds bacterial cell membrane causing rapid depolarization (bactericidal, concentration-dependent).",
        "spectrum": "✅ MRSA (excellent). ✅ VRE (good). ✅ Gram-positive. ❌ No Gram-negative. 🚫 Inactivated by pulmonary surfactant — NOT for pneumonia.",
        "coverage": ["MRSA", "VRE", "Gram-positive"],
        "indications": "Complicated skin/soft tissue infections, MRSA bacteremia/right-sided endocarditis, VRE infections (alternative to linezolid).",
        "side_effects": "⚠️ CPK elevation, myopathy/rhabdomyolysis, eosinophilic pneumonia (rare). Injection site reactions.",
        "pregnancy": "Category B. Use if clearly needed.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV only. Protein binding: ~92%.",
        "max_duration": "SSTI: 7-14 days. Bacteremia/endocarditis: 4-6+ weeks.",
        "dosing_adults": "4 mg/kg IV q24h (SSTI). 6-10 mg/kg IV q24h (bacteremia/endocarditis, higher end increasingly favored).",
        "dosing_peds": "Specialist-guided dosing; not well established <1 year.",
        "dosing_renal": "CrCl <30: extend interval to q48h.",
        "pharmacist_notes": "🚫 DO NOT use for pneumonia — inactivated by lung surfactant. 🩸 Baseline + weekly CPK monitoring (more frequent if on a statin or renally impaired). A Reserve-category agent — typically an ID/stewardship-guided choice.",
    },
    "aztreonam": {
        "generic": "Aztreonam", "brand": "Azactam",
        "drug_class": "Monobactam",
        "aware": "Reserve",
        "mechanism": "Monobactam; inhibits cell wall synthesis (bactericidal). Structurally distinct beta-lactam ring — minimal cross-reactivity with penicillins/cephalosporins.",
        "spectrum": "✅ Gram-negative only (including Pseudomonas). ❌ No Gram-positive, no anaerobes.",
        "coverage": ["Gram-negative", "Pseudomonas"],
        "indications": "Gram-negative infections (including Pseudomonas) in patients with severe beta-lactam allergy — its main clinical niche.",
        "side_effects": "Diarrhea, rash, elevated LFTs. Generally well tolerated.",
        "pregnancy": "Category B. Generally safe.",
        "cross_allergy": "✅ Minimal cross-reactivity with penicillins/cephalosporins (shares a side chain with ceftazidime only) — the go-to Gram-negative option in severe PCN/cephalosporin anaphylaxis.",
        "bioavailability": "IV/IM only. Protein binding: ~56%.",
        "max_duration": "7-14 days depending on source.",
        "dosing_adults": "1-2 g IV q8-12h (moderate infection); 2 g IV q6-8h (severe, max 8 g/day).",
        "dosing_peds": "30 mg/kg/dose IV q6-8h (Max 120 mg/kg/day).",
        "dosing_renal": "CrCl 10-30: 50% of usual dose. CrCl <10: 25% of usual dose (after a normal loading dose).",
        "pharmacist_notes": "✅ Key safety niche: one of the few Gram-negative options that's safe in true PCN/cephalosporin anaphylaxis (except shares cross-reactivity with ceftazidime specifically). No Gram-positive or anaerobic coverage — must be paired with another agent if needed.",
    },
    "rifampin": {
        "generic": "Rifampin", "brand": "Rifadin",
        "drug_class": "Rifamycin",
        "aware": "Not AWaRe-classified for general use (WHO classifies rifamycins primarily under its TB-specific guidance)",
        "mechanism": "Rifamycin; inhibits bacterial DNA-dependent RNA polymerase (bactericidal). Excellent biofilm/intracellular penetration.",
        "spectrum": "✅ Staph (including MRSA, as an adjunct only — never monotherapy, resistance emerges rapidly). ✅ Mycobacteria (TB). ✅ Some Gram-positive.",
        "coverage": ["Gram-positive", "Biofilm/intracellular adjunct"],
        "indications": "Adjunct for prosthetic joint/device infections and endocarditis with Staph (biofilm penetration), tuberculosis (first-line, with other agents), Neisseria meningitidis prophylaxis.",
        "side_effects": "Orange discoloration of body fluids (harmless), hepatotoxicity, flu-like reaction, potent CYP450 induction (major drug interaction risk).",
        "pregnancy": "Category C. Use if benefit outweighs risk (standard component of TB treatment in pregnancy).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~90-95%. Protein binding: ~80%.",
        "max_duration": "TB: 6+ months (per regimen). Prosthetic joint infection adjunct: weeks-months per ID guidance.",
        "dosing_adults": "600 mg PO/IV once daily OR 300-450 mg PO q12h (as an adjunct for Staph biofilm infections).",
        "dosing_peds": "10-20 mg/kg/day PO/IV divided q12-24h (Max 600 mg/day).",
        "dosing_renal": "No adjustment typically needed (primarily hepatic elimination).",
        "pharmacist_notes": "🚨 NEVER use as monotherapy for active bacterial infection — resistance develops within days; always pair with another active agent. 🚨 Potent CYP3A4/CYP2C9 inducer — screen for interactions (warfarin, oral contraceptives, antiretrovirals, azoles, statins, etc.) before every course.",
    },
    "penicillin_g": {
        "generic": "Penicillin G (Benzylpenicillin)", "brand": "Pfizerpen",
        "drug_class": "Natural Penicillin",
        "aware": "Access",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Strep (incl. S. pyogenes, viridans group), Neisseria, Treponema pallidum (syphilis). ❌ Most Staph (beta-lactamase producing). ❌ Gram-negative rods.",
        "coverage": ["Gram-positive"],
        "indications": "Syphilis, Strep pharyngitis/bacteremia, endocarditis (penicillin-susceptible), neurosyphilis, necrotizing fasciitis (adjunct to clindamycin).",
        "side_effects": "Anaphylaxis (true PCN allergy), Jarisch-Herxheimer reaction (syphilis treatment), electrolyte load with high-dose IV (potassium/sodium salt), seizures at very high doses/renal impairment.",
        "pregnancy": "Category B. Drug of choice for syphilis in pregnancy — no acceptable alternative (desensitize if allergic).",
        "cross_allergy": "⚠️ Base for all penicillin cross-reactivity; cross-reacts with other penicillins and, to a lesser degree, cephalosporins/carbapenems.",
        "bioavailability": "IV/IM only — negligible oral absorption (acid-labile).",
        "max_duration": "Single IM dose (early syphilis) up to 4 weeks IV (neurosyphilis/endocarditis).",
        "dosing_adults": "IV: 2-4 million units q4h (12-24 million units/day for severe infection). IM (benzathine, for syphilis): 2.4 million units single dose.",
        "dosing_peds": "IV: 100,000-400,000 units/kg/day divided q4-6h (max per adult dosing).",
        "dosing_renal": "CrCl <10: extend interval to q8-12h; monitor for neurotoxicity/seizures with accumulation.",
        "pharmacist_notes": "✅ Confirm which salt/formulation is ordered — aqueous crystalline (IV, short-acting) vs. procaine vs. benzathine (IM, depot) are NOT interchangeable and benzathine penicillin must never be given IV (can be fatal).",
    },
    "ampicillin": {
        "generic": "Ampicillin", "brand": "Principen",
        "drug_class": "Aminopenicillin (Penicillin)",
        "aware": "Access",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Strep, Enterococcus (drug of choice with gentamicin for susceptible endocarditis), Listeria. ✅ Some Gram-negative (E. coli, Proteus, H. influenzae — variable resistance). ❌ No anaerobes/beta-lactamase producers.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "Listeria meningitis/bacteremia, Enterococcal infections (with gentamicin), susceptible UTI, endocarditis prophylaxis.",
        "side_effects": "Diarrhea, rash (high rate with concurrent EBV/mononucleosis), C. diff, anaphylaxis in true PCN allergy.",
        "pregnancy": "Category B. Commonly used in pregnancy (e.g., GBS prophylaxis, Listeria).",
        "cross_allergy": "⚠️ Cross-reacts with other penicillins and cephalosporins (~5-10%).",
        "bioavailability": "Oral: ~40% (poor/variable — IV strongly preferred for serious infection). Protein binding: ~20%.",
        "max_duration": "Listeria meningitis: 3+ weeks. GBS prophylaxis: intrapartum only.",
        "dosing_adults": "IV: 1-2 g q4-6h (up to 12 g/day for meningitis/endocarditis).",
        "dosing_peds": "100-400 mg/kg/day IV divided q6h (meningitis dosing at the higher end).",
        "dosing_renal": "CrCl <10: extend interval to q12-24h.",
        "pharmacist_notes": "✅ Not interchangeable with amoxicillin for IV use — ampicillin is the parenteral aminopenicillin of choice. Reconstituted IV solution has a short stability window; check institutional beyond-use dating.",
    },
    "nafcillin": {
        "generic": "Nafcillin", "brand": "Nafcil",
        "drug_class": "Antistaphylococcal Penicillin",
        "aware": "Access",
        "mechanism": "Beta-lactamase-resistant beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Methicillin-susceptible Staph aureus (MSSA) — drug of choice. ✅ Strep. ❌ MRSA. ❌ Gram-negative, anaerobes.",
        "coverage": ["Gram-positive"],
        "indications": "MSSA bacteremia/endocarditis/osteomyelitis (preferred over vancomycin when susceptible — better outcomes).",
        "side_effects": "Phlebitis at IV site (irritant — central line often preferred for prolonged courses), interstitial nephritis, neutropenia with prolonged use, hepatotoxicity.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with other penicillins/cephalosporins.",
        "bioavailability": "IV only (poor, erratic oral absorption).",
        "max_duration": "Endocarditis: 4-6 weeks. Osteomyelitis: 4-6 weeks.",
        "dosing_adults": "1-2 g IV q4-6h (up to 12 g/day for endocarditis).",
        "dosing_peds": "100-200 mg/kg/day IV divided q6h.",
        "dosing_renal": "No adjustment typically needed (primarily hepatic elimination).",
        "pharmacist_notes": "🚨 Vesicant — monitor IV site closely for extravasation/phlebitis. Weekly CBC and LFTs recommended for courses beyond 2 weeks.",
    },
    "dicloxacillin": {
        "generic": "Dicloxacillin", "brand": "Dynapen",
        "drug_class": "Antistaphylococcal Penicillin",
        "aware": "Access",
        "mechanism": "Beta-lactamase-resistant beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ MSSA, Strep. ❌ MRSA. ❌ Gram-negative, anaerobes.",
        "coverage": ["Gram-positive"],
        "indications": "Mild-moderate MSSA skin/soft tissue infections (oral step-down or outpatient treatment).",
        "side_effects": "GI upset, rash, rarely hepatotoxicity/cholestatic jaundice.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with other penicillins/cephalosporins.",
        "bioavailability": "Oral: ~35-76% (take on empty stomach for best absorption).",
        "max_duration": "SSTI: 7-10 days.",
        "dosing_adults": "250-500 mg PO q6h.",
        "dosing_peds": "12.5-25 mg/kg/day PO divided q6h.",
        "dosing_renal": "No adjustment typically needed.",
        "pharmacist_notes": "✅ Take 1 hour before or 2 hours after meals — food significantly reduces absorption.",
    },
    "cefuroxime": {
        "generic": "Cefuroxime", "brand": "Ceftin / Zinacef",
        "drug_class": "Cephalosporin (2nd gen)",
        "aware": "Watch",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive (Strep, MSSA). ✅ Improved Gram-negative vs 1st gen (H. influenzae, Moraxella, E. coli). ❌ Pseudomonas, MRSA, atypicals.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "CAP, sinusitis, otitis media, uncomplicated UTI, early Lyme disease (PCN-allergic alternative).",
        "side_effects": "GI upset, diarrhea, rash, rare C. diff.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (low, ~1-3%) and other cephalosporins.",
        "bioavailability": "Oral (as axetil): ~37-52%, improved with food. IV: 100%.",
        "max_duration": "CAP/sinusitis: 5-10 days. Lyme: 14-21 days.",
        "dosing_adults": "Oral: 250-500 mg q12h. IV: 750 mg-1.5 g q8h.",
        "dosing_peds": "Oral: 20-30 mg/kg/day divided q12h. IV: 75-150 mg/kg/day divided q8h.",
        "dosing_renal": "CrCl 10-30: extend interval to q12h (IV) or reduce oral frequency; CrCl <10: q24h.",
        "pharmacist_notes": "✅ Oral tablets should be taken with food to improve bioavailability; do not crush (bitter taste, reduced absorption).",
    },
    "cefotaxime": {
        "generic": "Cefotaxime", "brand": "Claforan",
        "drug_class": "Cephalosporin (3rd gen)",
        "aware": "Watch",
        "mechanism": "Beta-lactam; inhibits cell wall synthesis (bactericidal). Good CSF penetration with inflamed meninges.",
        "spectrum": "✅ Gram-positive (Strep incl. pneumococcus). ✅ Broad Gram-negative (E. coli, Klebsiella, Neisseria, H. flu). ❌ Pseudomonas, MRSA, Enterococcus, atypicals.",
        "coverage": ["Gram-positive", "Gram-negative"],
        "indications": "CAP, meningitis, gonorrhea, spontaneous bacterial peritonitis, sepsis of unknown source — often preferred over ceftriaxone in neonates/hyperbilirubinemia (no bilirubin displacement) and where drug interactions with calcium-containing products are a concern.",
        "side_effects": "Diarrhea, rash, C. diff, rare drug-induced thrombocytopenia.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (low) and other cephalosporins.",
        "bioavailability": "IV/IM only.",
        "max_duration": "Meningitis: 10-14 days. CAP: 5-7 days.",
        "dosing_adults": "1-2 g IV q6-8h (up to 2 g q4h for meningitis).",
        "dosing_peds": "100-200 mg/kg/day IV divided q6-8h (meningitis at the higher end).",
        "dosing_renal": "CrCl <10: reduce dose by 50% or extend interval.",
        "pharmacist_notes": "✅ Preferred 3rd-gen cephalosporin in neonates (does not displace bilirubin from albumin, unlike ceftriaxone) and safer to co-administer with IV calcium.",
    },
    "cefpodoxime": {
        "generic": "Cefpodoxime", "brand": "Vantin",
        "drug_class": "Cephalosporin (3rd gen)",
        "aware": "Watch",
        "mechanism": "Oral beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive (Strep, MSSA). ✅ Gram-negative (E. coli, Klebsiella, H. flu, Moraxella). ❌ Pseudomonas, MRSA, Enterococcus, atypicals.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "Oral step-down for CAP, uncomplicated UTI, otitis media/sinusitis, gonorrhea (uncomplicated).",
        "side_effects": "GI upset, diarrhea, rash.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (low) and other cephalosporins.",
        "bioavailability": "Oral: ~50%, significantly improved with food.",
        "max_duration": "5-10 days depending on indication.",
        "dosing_adults": "100-400 mg PO q12h.",
        "dosing_peds": "10 mg/kg/day divided q12h (max per adult dosing).",
        "dosing_renal": "CrCl <30: extend interval to q24h.",
        "pharmacist_notes": "✅ Take with food to improve absorption. Avoid concurrent high-dose antacids/H2 blockers (reduce absorption via gastric pH).",
    },
    "cefdinir": {
        "generic": "Cefdinir", "brand": "Omnicef",
        "drug_class": "Cephalosporin (3rd gen)",
        "aware": "Watch",
        "mechanism": "Oral beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-positive (Strep, MSSA). ✅ Gram-negative (H. flu, Moraxella, E. coli). ❌ Pseudomonas, MRSA, Enterococcus, atypicals.",
        "coverage": ["Gram-positive", "Gram-negative (limited)"],
        "indications": "CAP, otitis media, sinusitis, pharyngitis, uncomplicated SSTI (widely used pediatric oral option).",
        "side_effects": "Diarrhea (common), rash (reddish stool with concurrent iron supplements is a benign, well-known interaction), rare C. diff.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (low) and other cephalosporins.",
        "bioavailability": "Oral: ~16-21% (capsule), ~25% (suspension).",
        "max_duration": "5-10 days depending on indication.",
        "dosing_adults": "300 mg PO q12h OR 600 mg PO once daily.",
        "dosing_peds": "14 mg/kg/day PO divided q12-24h (max 600 mg/day).",
        "dosing_renal": "CrCl <30: reduce to 300 mg once daily.",
        "pharmacist_notes": "✅ Separate from iron-containing products and antacids by ≥2 hours — both reduce absorption and iron can cause harmless reddish discoloration of stool when combined.",
    },
    "cefixime": {
        "generic": "Cefixime", "brand": "Suprax",
        "drug_class": "Cephalosporin (3rd gen)",
        "aware": "Watch",
        "mechanism": "Oral beta-lactam; inhibits cell wall synthesis (bactericidal).",
        "spectrum": "✅ Gram-negative (E. coli, Klebsiella, Neisseria gonorrhoeae, H. flu). ⚠️ Weaker Gram-positive coverage than other 3rd-gen orals. ❌ Pseudomonas, MRSA, Enterococcus.",
        "coverage": ["Gram-negative"],
        "indications": "Uncomplicated UTI, uncomplicated gonorrhea (alternative when ceftriaxone unavailable), typhoid fever (susceptible strains), shigellosis.",
        "side_effects": "Diarrhea (more common than other oral cephalosporins), abdominal pain, rare C. diff.",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins (low) and other cephalosporins.",
        "bioavailability": "Oral: ~40-50%.",
        "max_duration": "UTI: 7-14 days. Gonorrhea: single dose. Typhoid: 7-14 days.",
        "dosing_adults": "400 mg PO once daily OR 200 mg PO q12h.",
        "dosing_peds": "8 mg/kg/day PO divided q12-24h (max 400 mg/day).",
        "dosing_renal": "CrCl <20: reduce dose by 25%.",
        "pharmacist_notes": "🚫 Not recommended as a first-line single-dose option for gonorrhea per current CDC guidance (ceftriaxone preferred) due to declining susceptibility trends — verify local resistance patterns.",
    },
    "ceftaroline": {
        "generic": "Ceftaroline", "brand": "Teflaro",
        "drug_class": "Cephalosporin (5th gen)",
        "aware": "Not officially on the WHO core AWaRe list; commonly treated as Reserve-tier by institutional formularies given its narrow, MRSA-targeted role",
        "mechanism": "Beta-lactam with high affinity for PBP2a; inhibits cell wall synthesis (bactericidal) — the only cephalosporin with reliable MRSA activity.",
        "spectrum": "✅ MRSA, Strep (incl. resistant pneumococcus). ✅ Gram-negative (similar to ceftriaxone, excluding Pseudomonas/ESBL). ❌ Pseudomonas, Enterococcus, atypicals.",
        "coverage": ["Gram-positive", "MRSA", "Gram-negative (limited)"],
        "indications": "Complicated SSTI and CAP, including MRSA; salvage option for MRSA bacteremia/endocarditis not responding to vancomycin/daptomycin (specialist-guided).",
        "side_effects": "Diarrhea, rash, rare drug-induced eosinophilic pneumonia and neutropenia with prolonged courses, direct Coombs seroconversion (rarely hemolytic anemia).",
        "pregnancy": "Category B.",
        "cross_allergy": "⚠️ Cross-reacts with penicillins/other cephalosporins.",
        "bioavailability": "IV only.",
        "max_duration": "SSTI: 5-14 days. Endocarditis/bacteremia salvage: per ID guidance.",
        "dosing_adults": "600 mg IV q12h (extended infusion, 600 mg q8h, used off-label for severe/resistant infections).",
        "dosing_peds": "≥2 months: 8-12 mg/kg/dose IV q8h (max per adult dosing).",
        "dosing_renal": "CrCl 31-50: 400 mg q12h. CrCl 15-30: 300 mg q12h. ESRD/HD: 200 mg q12h, given after dialysis.",
        "pharmacist_notes": "🔒 Typically restricted/ID-approval formulary agent given cost and narrow niche use — confirm local stewardship policy before dispensing.",
    },
    "imipenem_cilastatin": {
        "generic": "Imipenem-Cilastatin", "brand": "Primaxin",
        "drug_class": "Carbapenem",
        "aware": "Watch",
        "mechanism": "Beta-lactam (carbapenem); inhibits cell wall synthesis (bactericidal). Cilastatin blocks renal dehydropeptidase-mediated degradation of imipenem.",
        "spectrum": "✅ Very broad: Gram-positive (incl. some resistant strains), Gram-negative (incl. Pseudomonas, ESBL producers), anaerobes. ❌ MRSA, some Stenotrophomonas, atypicals.",
        "coverage": ["Gram-positive", "Gram-negative", "Pseudomonas", "Anaerobes"],
        "indications": "Severe polymicrobial/nosocomial infections, febrile neutropenia, intra-abdominal infections, ESBL-producing organism infections.",
        "side_effects": "🚨 Seizures (higher risk than other carbapenems, especially at high doses/renal impairment/CNS disease) — generally avoided for meningitis. GI upset, C. diff.",
        "pregnancy": "Category C.",
        "cross_allergy": "⚠️ Low cross-reactivity with penicillins/cephalosporins; use caution with severe/anaphylactic PCN allergy.",
        "bioavailability": "IV only.",
        "max_duration": "Per indication and clinical response, typically 7-14 days.",
        "dosing_adults": "500 mg IV q6h (up to 1 g q6-8h for severe infection).",
        "dosing_peds": "60-100 mg/kg/day IV divided q6h (max 4 g/day).",
        "dosing_renal": "CrCl 30-70: extend interval to q8h; CrCl 15-30: q12h; avoid if CrCl <15 unless on dialysis.",
        "pharmacist_notes": "🚨 Avoid in patients with known seizure disorder/CNS lesions where possible — meropenem or ertapenem are preferred carbapenems for CNS-risk patients.",
    },
    "moxifloxacin": {
        "generic": "Moxifloxacin", "brand": "Avelox",
        "drug_class": "Fluoroquinolone",
        "aware": "Watch",
        "mechanism": "Fluoroquinolone; inhibits DNA gyrase/topoisomerase IV (bactericidal). Enhanced Gram-positive/atypical/anaerobic activity vs. ciprofloxacin.",
        "spectrum": "✅ Strep pneumoniae (incl. resistant strains), atypicals, anaerobes. ⚠️ No reliable Pseudomonas coverage (unlike ciprofloxacin/levofloxacin). ✅ Gram-negative (moderate).",
        "coverage": ["Gram-positive", "Atypicals", "Anaerobes", "Gram-negative (limited)"],
        "indications": "CAP (respiratory fluoroquinolone of choice), intra-abdominal infections, MDR-TB (2nd-line agent).",
        "side_effects": "🚨 QT prolongation (more than other fluoroquinolones — avoid with other QT-prolonging drugs), tendon rupture, peripheral neuropathy, CNS effects, aortic aneurysm/dissection risk.",
        "pregnancy": "Category C. Avoid in pregnancy/breastfeeding.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~90% (excellent). Protein binding: ~50%.",
        "max_duration": "CAP: 5-10 days.",
        "dosing_adults": "400 mg PO/IV once daily.",
        "dosing_peds": "Not routinely recommended (fluoroquinolone class effects on growing cartilage) — reserve for specific indications (e.g., MDR-TB) under specialist guidance.",
        "dosing_renal": "No dose adjustment needed (primarily non-renal elimination) — unlike most other fluoroquinolones.",
        "pharmacist_notes": "⚠️ Unlike ciprofloxacin/levofloxacin, moxifloxacin does NOT achieve adequate urinary concentrations — do not use for UTI. Avoid dairy/antacids/iron/zinc within 2 hours (oral absorption).",
    },
    "ofloxacin": {
        "generic": "Ofloxacin", "brand": "Floxin",
        "drug_class": "Fluoroquinolone",
        "aware": "Watch",
        "mechanism": "Fluoroquinolone; inhibits DNA gyrase (topoisomerase II), bactericidal.",
        "spectrum": "✅ Gram-negative (E. coli, Neisseria). ⚠️ Moderate Gram-positive. ✅ Some atypicals (Chlamydia). ❌ Pseudomonas (weaker than ciprofloxacin), anaerobes.",
        "coverage": ["Gram-negative", "Gram-positive (moderate)", "Atypicals"],
        "indications": "Uncomplicated UTI, cervicitis/urethritis (Chlamydia/gonorrhea — largely superseded by other regimens), otitis externa (otic formulation), conjunctivitis (ophthalmic formulation).",
        "side_effects": "Tendon rupture, peripheral neuropathy, CNS agitation, QT prolongation, photosensitivity.",
        "pregnancy": "Category C. Avoid in pregnancy/breastfeeding.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~98% (excellent). Protein binding: ~25%.",
        "max_duration": "UTI: 3-7 days.",
        "dosing_adults": "200-400 mg PO/IV q12h.",
        "dosing_peds": "Not routinely recommended (fluoroquinolone class effects) — reserve for specific indications.",
        "dosing_renal": "CrCl 20-50: extend interval to q24h; CrCl <20: reduce dose by 50% and extend interval.",
        "pharmacist_notes": "✅ Largely superseded by ciprofloxacin/levofloxacin for systemic use in most formularies — check whether the topical (otic/ophthalmic) formulation, not the oral tablet, is actually intended.",
    },
    "clarithromycin": {
        "generic": "Clarithromycin", "brand": "Biaxin",
        "drug_class": "Macrolide",
        "aware": "Watch",
        "mechanism": "Macrolide; binds 50S ribosome, inhibits protein synthesis (bacteriostatic, some bactericidal activity).",
        "spectrum": "✅ Gram-positive (Strep, Staph), atypicals (Mycoplasma, Chlamydia, Legionella), H. pylori (as combination therapy), Mycobacterium avium complex (MAC).",
        "coverage": ["Gram-positive", "Atypicals"],
        "indications": "CAP, H. pylori eradication (triple/quadruple therapy), MAC prophylaxis/treatment, sinusitis/otitis media (PCN-allergic alternative).",
        "side_effects": "🚨 QT prolongation, metallic taste, GI upset, hepatotoxicity, significant CYP3A4 drug interactions.",
        "pregnancy": "Category C. Avoid if possible — some data suggest cardiovascular malformation risk with 1st-trimester use; azithromycin often preferred in pregnancy.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~50-55%. Protein binding: ~70%.",
        "max_duration": "CAP: 7-14 days. H. pylori: 10-14 days.",
        "dosing_adults": "250-500 mg PO q12h OR 1000 mg extended-release once daily.",
        "dosing_peds": "15 mg/kg/day PO divided q12h (max 500 mg/dose).",
        "dosing_renal": "CrCl <30: reduce dose by 50%.",
        "pharmacist_notes": "🚨 Extensive CYP3A4 interactions (statins, warfarin, colchicine, benzodiazepines) — screen every regimen. Do not co-administer with colchicine in renal/hepatic impairment (reported fatalities).",
    },
    "erythromycin": {
        "generic": "Erythromycin", "brand": "Erythrocin",
        "drug_class": "Macrolide",
        "aware": "Watch",
        "mechanism": "Macrolide; binds 50S ribosome, inhibits protein synthesis (bacteriostatic).",
        "spectrum": "✅ Gram-positive (Strep), atypicals (Mycoplasma, Chlamydia, Legionella), Bordetella pertussis. ⚠️ Weaker/more resistance than azithromycin/clarithromycin.",
        "coverage": ["Gram-positive", "Atypicals"],
        "indications": "Pertussis, chlamydial conjunctivitis/pneumonia in neonates, GI prokinetic use (off-label, low dose), PCN-allergic alternative for mild Strep infections.",
        "side_effects": "🚨 Significant GI upset (motilin agonist — often dose-limiting), QT prolongation, cholestatic hepatitis, infantile hypertrophic pyloric stenosis with neonatal use.",
        "pregnancy": "Category B, except estolate salt (associated with maternal hepatotoxicity — avoid in pregnancy).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: variable by salt form (~18-45%). Protein binding: ~70-90%.",
        "max_duration": "Pertussis: 7-14 days.",
        "dosing_adults": "250-500 mg PO q6h (base/stearate) or IV.",
        "dosing_peds": "30-50 mg/kg/day PO divided q6-8h.",
        "dosing_renal": "No adjustment typically needed.",
        "pharmacist_notes": "✅ GI intolerance is common and often limits use — clarithromycin/azithromycin are usually better tolerated for the same indications. Significant CYP3A4 interactions, similar to clarithromycin.",
    },
    "tigecycline": {
        "generic": "Tigecycline", "brand": "Tygacil",
        "drug_class": "Glycylcycline",
        "aware": "Reserve",
        "mechanism": "Tetracycline derivative; binds 30S ribosome, inhibits protein synthesis (bacteriostatic). Active against many tetracycline- and multidrug-resistant organisms.",
        "spectrum": "✅ Broad: MRSA, VRE, ESBL producers, anaerobes. ❌ Pseudomonas, Proteus (intrinsically resistant). ⚠️ Low serum/urine concentrations — avoid for bacteremia/UTI.",
        "coverage": ["Gram-positive", "MRSA", "Gram-negative (limited)", "Anaerobes"],
        "indications": "Complicated intra-abdominal infections, complicated SSTI, salvage option for MDR Gram-negative infections when few alternatives remain (ID-guided).",
        "side_effects": "🚨 Boxed warning: increased mortality vs. comparators in some trials — reserve for when alternatives are not suitable. Nausea/vomiting (common), pancreatitis, hepatotoxicity, tooth discoloration in children (tetracycline-class effect).",
        "pregnancy": "Category D. Avoid — tetracycline-class fetal bone/teeth effects.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV only.",
        "max_duration": "Per indication and ID guidance, typically 5-14 days.",
        "dosing_adults": "Loading dose 100 mg IV, then 50 mg IV q12h.",
        "dosing_peds": "Not established/not routinely recommended under age 8 (tetracycline-class dental effects); specialist-guided only.",
        "dosing_renal": "No adjustment needed for renal impairment; reduce maintenance to 25 mg q12h in severe hepatic impairment (Child-Pugh C).",
        "pharmacist_notes": "🔒 Reserve/ID-restricted agent at most institutions given the boxed mortality warning and narrow niche — confirm local stewardship policy. Not effective for bloodstream infections due to low serum concentrations.",
    },
    "minocycline": {
        "generic": "Minocycline", "brand": "Minocin",
        "drug_class": "Tetracycline",
        "aware": "Access",
        "mechanism": "Tetracycline; binds 30S ribosome, inhibits protein synthesis (bacteriostatic). Excellent tissue/CNS penetration.",
        "spectrum": "✅ MRSA (many strains, confirm local susceptibility), atypicals, Acinetobacter (some MDR strains), acne-associated organisms.",
        "coverage": ["Gram-positive", "MRSA", "Atypicals"],
        "indications": "Acne vulgaris, MRSA SSTI (oral option), Acinetobacter infections (salvage/combination), doxycycline-intolerant patients needing tetracycline-class coverage.",
        "side_effects": "Dizziness/vestibular effects (more than doxycycline), photosensitivity, blue-gray skin/mucosal pigmentation with long-term use, tooth discoloration (age <8), drug-induced lupus.",
        "pregnancy": "Category D. Avoid (fetal bone/teeth effects).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~90-100%.",
        "max_duration": "Acne: weeks-months. SSTI: 7-14 days.",
        "dosing_adults": "Loading dose 200 mg PO, then 100 mg PO q12h.",
        "dosing_peds": ">8 yrs only: 4 mg/kg loading, then 2 mg/kg/dose q12h.",
        "dosing_renal": "No adjustment typically needed.",
        "pharmacist_notes": "⚠️ Vestibular side effects (dizziness, ataxia) are more common than with doxycycline — counsel patients, especially those driving/operating machinery.",
    },
    "colistin": {
        "generic": "Colistin (Colistimethate)", "brand": "Coly-Mycin M",
        "drug_class": "Polymyxin",
        "aware": "Reserve",
        "mechanism": "Polymyxin; disrupts bacterial outer cell membrane (bactericidal). Last-resort agent for MDR Gram-negative organisms.",
        "spectrum": "✅ MDR Gram-negative (carbapenem-resistant Enterobacteriaceae, MDR Pseudomonas, MDR Acinetobacter). ❌ Gram-positive, Proteus, Serratia, Burkholderia (intrinsic resistance).",
        "coverage": ["Gram-negative", "Pseudomonas"],
        "indications": "Last-line therapy for MDR/XDR Gram-negative infections (pan-resistant organisms) — ID consultation essentially always required.",
        "side_effects": "🚨 Nephrotoxicity (dose-limiting, common), neurotoxicity (paresthesias, dizziness, neuromuscular blockade/respiratory paralysis at high doses).",
        "pregnancy": "Category C.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV/inhaled/intrathecal — negligible oral absorption.",
        "max_duration": "Per ID guidance, typically 7-14 days; longer for specific sources.",
        "dosing_adults": "Loading dose ~5 mg/kg colistin base activity (CBA) IV, then 2.5-5 mg/kg/day CBA divided q12h (exact dosing per pharmacokinetic protocol — significant institutional variability in units/formulas).",
        "dosing_peds": "Specialist-guided only; weight-based CBA dosing similar in principle to adults.",
        "dosing_renal": "Requires renal-function-based dose adjustment per institutional nomogram — do not dose empirically without checking the specific product's dosing chart.",
        "pharmacist_notes": "🚨 High risk of dosing errors — colistin base activity (CBA) vs. colistimethate sodium (CMS) vs. international units are all different units used interchangeably in literature. Always confirm which unit your institution's protocol/pharmacy uses before dosing. Restricted/ID-approval agent at most institutions.",
    },
    "chloramphenicol": {
        "generic": "Chloramphenicol", "brand": "Chloromycetin",
        "drug_class": "Amphenicol",
        "aware": "Access",
        "mechanism": "Binds 50S ribosome, inhibits protein synthesis (bacteriostatic, bactericidal against some organisms incl. H. flu, N. meningitidis, S. pneumoniae). Excellent CNS penetration.",
        "spectrum": "✅ Broad spectrum: Gram-positive, Gram-negative, anaerobes, rickettsiae. Largely historical use in high-resource settings due to toxicity; still used where alternatives are unavailable/unaffordable.",
        "coverage": ["Gram-positive", "Gram-negative", "Anaerobes"],
        "indications": "Bacterial meningitis (PCN/cephalosporin-allergic, in resource-limited settings), typhoid fever, rickettsial disease, eye infections (topical), where newer agents are unavailable.",
        "side_effects": "🚨 Aplastic anemia (rare, idiosyncratic, potentially fatal — dose-independent), dose-dependent reversible bone marrow suppression, 🚨 Gray baby syndrome in neonates (immature glucuronidation).",
        "pregnancy": "Category C. Avoid near term (risk of gray baby syndrome in neonate).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~75-90%. Protein binding: ~50-60%.",
        "max_duration": "Per indication and clinical response.",
        "dosing_adults": "50-100 mg/kg/day IV/PO divided q6h (max 4 g/day).",
        "dosing_peds": "50-75 mg/kg/day divided q6h — use extreme caution in neonates (immature hepatic conjugation, risk of gray baby syndrome); dose reduction and level monitoring required.",
        "dosing_renal": "No adjustment typically needed (primarily hepatic elimination) — but monitor levels closely regardless given narrow therapeutic index.",
        "pharmacist_notes": "🚨 Requires baseline and serial CBC monitoring for bone marrow suppression; drug-level monitoring recommended, especially in neonates/hepatic impairment. Largely reserved for settings/situations where safer alternatives are not options.",
    },
    "fosfomycin": {
        "generic": "Fosfomycin (oral)", "brand": "Monurol",
        "drug_class": "Phosphonic Acid Derivative",
        "aware": "Access",
        "mechanism": "Inhibits an early step of bacterial cell wall synthesis (enolpyruvate transferase, MurA) — bactericidal, structurally unrelated to other antibiotic classes.",
        "spectrum": "✅ E. coli (incl. many ESBL/MDR strains), Enterococcus (incl. VRE, for UTI only). ⚠️ Variable activity vs. Klebsiella, Proteus. High urinary concentrations, low systemic levels.",
        "coverage": ["Gram-negative", "Gram-positive"],
        "indications": "Uncomplicated cystitis, including many MDR/ESBL organisms, as a single-dose oral option.",
        "side_effects": "Diarrhea, headache, GI upset — generally well tolerated.",
        "pregnancy": "Category B. Considered a reasonable UTI option in pregnancy.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral (granules, as trometamol salt): ~40%. Achieves very high urinary concentrations.",
        "max_duration": "Single dose for uncomplicated cystitis.",
        "dosing_adults": "3 g PO single dose, dissolved in water.",
        "dosing_peds": "Not routinely established for oral use in children — specialist-guided.",
        "dosing_renal": "No adjustment for single-dose UTI use.",
        "pharmacist_notes": "⚠️ Oral fosfomycin trometamol (for UTI, Access-classified) is NOT the same product or dose as IV fosfomycin disodium (Reserve-classified, used for severe MDR infections) — the two must not be confused.",
    },
    "amikacin": {
        "generic": "Amikacin", "brand": "Amikin",
        "drug_class": "Aminoglycoside",
        "aware": "Access",
        "mechanism": "Aminoglycoside; binds 30S ribosome, inhibits protein synthesis (bactericidal, concentration-dependent). Often active against gentamicin/tobramycin-resistant organisms.",
        "spectrum": "✅ Gram-negative (incl. many resistant Pseudomonas, Acinetobacter), Mycobacteria (adjunct for MDR-TB/atypical mycobacteria). ❌ Anaerobes, most Gram-positive (used only synergistically).",
        "coverage": ["Gram-negative", "Pseudomonas"],
        "indications": "MDR Gram-negative infections (combination therapy), MDR-TB/nontuberculous mycobacteria (specialist-guided), empiric broad Gram-negative coverage in resistant local flora.",
        "side_effects": "🚨 Nephrotoxicity, ototoxicity (auditory/vestibular — can be irreversible), neuromuscular blockade at high doses.",
        "pregnancy": "Category D. Avoid unless benefit clearly outweighs risk (fetal ototoxicity reported).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV/IM only.",
        "max_duration": "Typically short courses (5-14 days) given toxicity — used for synergy/severe MDR infection, not prolonged monotherapy where avoidable.",
        "dosing_adults": "15 mg/kg IV q24h (extended-interval dosing, weight- and renal-function-based; consult institutional nomogram) OR 7.5 mg/kg q12h (traditional dosing).",
        "dosing_peds": "15-22.5 mg/kg/day divided q8h or extended-interval per institutional protocol.",
        "dosing_renal": "Requires renal-function-based dosing and trough/peak level monitoring — do not dose empirically without institutional nomogram/pharmacokinetic consult.",
        "pharmacist_notes": "🚨 Requires peak/trough (or extended-interval single-level) monitoring; obtain baseline renal function and audiology assessment for prolonged courses.",
    },
    "tobramycin": {
        "generic": "Tobramycin", "brand": "Nebcin",
        "drug_class": "Aminoglycoside",
        "aware": "Access",
        "mechanism": "Aminoglycoside; binds 30S ribosome, inhibits protein synthesis (bactericidal, concentration-dependent). More active against Pseudomonas than gentamicin.",
        "spectrum": "✅ Gram-negative, especially Pseudomonas aeruginosa. ❌ Anaerobes, most Gram-positive (used only synergistically).",
        "coverage": ["Gram-negative", "Pseudomonas"],
        "indications": "Pseudomonas infections (combination therapy), cystic fibrosis pulmonary exacerbations (inhaled formulation), ocular infections (topical formulation).",
        "side_effects": "🚨 Nephrotoxicity, ototoxicity (auditory/vestibular), neuromuscular blockade at high doses.",
        "pregnancy": "Category D. Avoid unless benefit clearly outweighs risk.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV/IM/inhaled/ophthalmic — negligible oral absorption.",
        "max_duration": "Short courses given toxicity; inhaled formulation used in cycles (28 days on/off) for cystic fibrosis.",
        "dosing_adults": "IV: 5-7 mg/kg once daily (extended-interval, per institutional nomogram) OR 1-1.7 mg/kg q8h (traditional dosing).",
        "dosing_peds": "IV: similar extended-interval or traditional dosing per institutional protocol, weight-based.",
        "dosing_renal": "Requires renal-function-based dosing and level monitoring — do not dose empirically without institutional nomogram.",
        "pharmacist_notes": "🚨 Requires peak/trough monitoring for IV use; inhaled formulation dosed differently and does not require systemic level monitoring in most protocols.",
    },
    "isoniazid": {
        "generic": "Isoniazid", "brand": "INH",
        "drug_class": "Antitubercular",
        "aware": "Not AWaRe-classified for general use (WHO addresses TB drugs under its separate TB-specific guidance, not the general antibacterial AWaRe list)",
        "mechanism": "Inhibits mycolic acid synthesis in the mycobacterial cell wall (bactericidal against actively dividing M. tuberculosis).",
        "spectrum": "✅ Mycobacterium tuberculosis (first-line agent). Some activity against other mycobacteria.",
        "coverage": ["Mycobacteria"],
        "indications": "Active TB (always as part of multi-drug therapy — never monotherapy for active disease), latent TB infection (LTBI) treatment/prophylaxis.",
        "side_effects": "🚨 Hepatotoxicity (dose- and age-dependent, monitor LFTs), peripheral neuropathy (prevent with pyridoxine/vitamin B6 supplementation), drug-induced lupus, CYP450 interactions.",
        "pregnancy": "Category C. Used in pregnancy when TB treatment is indicated — give with pyridoxine supplementation.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >90%.",
        "max_duration": "Active TB: 6+ months (combination regimen). LTBI: 3-9 months depending on regimen.",
        "dosing_adults": "5 mg/kg/day (typically 300 mg) PO/IV once daily, max 300 mg/day (active TB); LTBI regimens vary (daily or weekly with rifapentine).",
        "dosing_peds": "10-15 mg/kg/day PO once daily, max 300 mg/day.",
        "dosing_renal": "No adjustment typically needed (primarily hepatic elimination).",
        "pharmacist_notes": "🚨 Always co-prescribe pyridoxine (vitamin B6, typically 25-50 mg/day) to prevent peripheral neuropathy, especially in diabetics, pregnancy, malnutrition, or HIV. Monitor LFTs at baseline and periodically.",
    },
    "ethambutol": {
        "generic": "Ethambutol", "brand": "Myambutol",
        "drug_class": "Antitubercular",
        "aware": "Not AWaRe-classified for general use (WHO addresses TB drugs under its separate TB-specific guidance, not the general antibacterial AWaRe list)",
        "mechanism": "Inhibits arabinosyl transferase, disrupting mycobacterial cell wall arabinogalactan synthesis (bacteriostatic).",
        "spectrum": "✅ Mycobacterium tuberculosis and some nontuberculous mycobacteria (first-line TB agent, used to prevent resistance emergence to other agents).",
        "coverage": ["Mycobacteria"],
        "indications": "Active TB — part of standard 4-drug induction regimen (RIPE: rifampin, isoniazid, pyrazinamide, ethambutol) until susceptibilities are known.",
        "side_effects": "🚨 Optic neuritis (dose-dependent, can cause irreversible vision loss — red-green color discrimination lost first) — requires baseline and periodic visual acuity/color vision testing.",
        "pregnancy": "Category B/C (sources vary). Generally considered acceptable as part of standard TB regimens in pregnancy.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~75-80%.",
        "max_duration": "Typically first 2 months of a 6-month regimen (until susceptibilities confirm it can be dropped).",
        "dosing_adults": "15-25 mg/kg PO once daily (weight-based dosing bands per WHO/ATS guidance).",
        "dosing_peds": "15-20 mg/kg PO once daily — use with caution; visual acuity monitoring is difficult in very young children who cannot reliably report symptoms.",
        "dosing_renal": "CrCl <30 or on dialysis: reduce to 15-25 mg/kg 3x/week rather than daily.",
        "pharmacist_notes": "🚨 Obtain baseline visual acuity and color vision testing before starting, and monitor monthly if therapy extends beyond 2 months or at higher doses — instruct patients to report any visual changes immediately.",
    },
    "pyrazinamide": {
        "generic": "Pyrazinamide", "brand": "PZA",
        "drug_class": "Antitubercular",
        "aware": "Not AWaRe-classified for general use (WHO addresses TB drugs under its separate TB-specific guidance, not the general antibacterial AWaRe list)",
        "mechanism": "Converted to active form (pyrazinoic acid) by mycobacterial pyrazinamidase; disrupts mycobacterial membrane function (bactericidal, especially against semi-dormant intracellular organisms in acidic environments).",
        "spectrum": "✅ Mycobacterium tuberculosis (first-line agent, particularly effective against intracellular/semi-dormant bacilli).",
        "coverage": ["Mycobacteria"],
        "indications": "Active TB — part of standard 4-drug induction regimen (RIPE), typically for the first 2 months.",
        "side_effects": "🚨 Hepatotoxicity (can be significant — monitor LFTs), hyperuricemia/gout flares, arthralgia, GI upset, photosensitivity.",
        "pregnancy": "Category C. WHO recommends inclusion in standard TB regimens during pregnancy; US guidance has historically been more cautious — follow local/current guidance.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >90%.",
        "max_duration": "Typically first 2 months of a 6-month regimen.",
        "dosing_adults": "Weight-based dosing bands: 40-55 kg 1 g; 56-75 kg 1.5 g; 76-90 kg 2 g — given once daily or per intermittent regimen.",
        "dosing_peds": "30-40 mg/kg/day PO once daily (max per adult weight-band dosing).",
        "dosing_renal": "CrCl <30 or on dialysis: dose 3x/week rather than daily at the same weight-based dose.",
        "pharmacist_notes": "✅ Monitor LFTs (with isoniazid/rifampin, part of the standard hepatotoxicity-monitoring regimen for RIPE therapy) and uric acid if the patient develops joint symptoms.",
    },
    "fluconazole": {
        "generic": "Fluconazole", "brand": "Diflucan",
        "drug_class": "Triazole Antifungal",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Inhibits fungal cytochrome P450-dependent 14-alpha-demethylase, blocking ergosterol synthesis (fungistatic).",
        "spectrum": "✅ Most Candida species (except C. krusei — intrinsically resistant, and increasingly C. glabrata — dose-dependent), Cryptococcus. ❌ Aspergillus, molds.",
        "coverage": ["Fungal"],
        "indications": "Vulvovaginal candidiasis, oropharyngeal/esophageal candidiasis, candidemia (susceptible species), cryptococcal meningitis (consolidation/maintenance phase), antifungal prophylaxis in high-risk patients.",
        "side_effects": "GI upset, headache, QT prolongation, hepatotoxicity, significant CYP450 drug interactions.",
        "pregnancy": "Category C (single low dose) / D (higher or repeated doses — associated with congenital malformations). Avoid repeated dosing in pregnancy.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: >90% (excellent, IV and oral doses are interchangeable).",
        "max_duration": "Vaginal candidiasis: single dose. Candidemia: 2 weeks after first negative blood culture. Cryptococcal maintenance: up to 12 months.",
        "dosing_adults": "Vaginal candidiasis: 150 mg PO single dose. Candidemia/systemic: loading 800 mg (12 mg/kg), then 400 mg (6 mg/kg) once daily.",
        "dosing_peds": "6-12 mg/kg/day once daily depending on indication.",
        "dosing_renal": "CrCl <50: reduce maintenance dose by 50% (loading dose unchanged).",
        "pharmacist_notes": "🚨 Significant CYP3A4/CYP2C9 inhibitor — screen for interactions (warfarin, sulfonylureas, phenytoin, statins) before every course.",
    },
    "itraconazole": {
        "generic": "Itraconazole", "brand": "Sporanox",
        "drug_class": "Triazole Antifungal",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Inhibits fungal cytochrome P450-dependent ergosterol synthesis (fungistatic).",
        "spectrum": "✅ Dermatophytes, Candida, Aspergillus (alternative agent), endemic fungi (Histoplasma, Blastomyces, Sporothrix). ❌ Mucormycosis (no activity — a key distinguishing gap vs. amphotericin B).",
        "coverage": ["Fungal"],
        "indications": "Onychomycosis, dermatophyte infections, endemic mycoses (histoplasmosis, blastomycosis, sporotrichosis), allergic bronchopulmonary aspergillosis, chronic/step-down aspergillosis therapy.",
        "side_effects": "🚨 Negative inotrope (avoid/use caution in heart failure), hepatotoxicity, GI upset, significant CYP3A4 drug interactions, erratic/formulation-dependent oral absorption.",
        "pregnancy": "Category C. Avoid unless clearly needed (teratogenic in animal studies).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral capsule: variable, improved with food and acidic gastric pH. Oral solution: better absorbed on an empty stomach. Levels should be checked for serious infections.",
        "max_duration": "Onychomycosis: pulse dosing over 3 months. Endemic mycoses: 6-12+ months.",
        "dosing_adults": "200 mg PO once or twice daily depending on indication (capsule with food; solution on empty stomach).",
        "dosing_peds": "3-5 mg/kg/day divided q12-24h (specialist-guided).",
        "dosing_renal": "Use caution in renal impairment (IV formulation accumulates cyclodextrin vehicle — avoid IV if CrCl <30); oral generally does not require adjustment.",
        "pharmacist_notes": "⚠️ Capsule and oral solution are NOT bioequivalent and have opposite food requirements — confirm formulation before counseling. Therapeutic drug monitoring recommended for serious/systemic infections.",
    },
    "voriconazole": {
        "generic": "Voriconazole", "brand": "Vfend",
        "drug_class": "Triazole Antifungal",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Inhibits fungal cytochrome P450-dependent ergosterol synthesis (fungistatic/fungicidal depending on organism).",
        "spectrum": "✅ Aspergillus (drug of choice for invasive aspergillosis), Candida (incl. some fluconazole-resistant species). ❌ Mucormycosis (no activity).",
        "coverage": ["Fungal"],
        "indications": "Invasive aspergillosis (first-line), invasive/refractory candidiasis, esophageal candidiasis, salvage therapy for serious fungal infections.",
        "side_effects": "🚨 Visual disturbances (common, usually transient — blurred vision, photophobia, altered color perception), hepatotoxicity, photosensitivity/phototoxic skin reactions (risk of skin cancer with prolonged use), hallucinations, QT prolongation.",
        "pregnancy": "Category D. Avoid — teratogenic.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~96% (excellent, take on empty stomach).",
        "max_duration": "Invasive aspergillosis: typically ≥6-12 weeks, guided by clinical/radiographic response.",
        "dosing_adults": "IV: loading 6 mg/kg q12h x2 doses, then 4 mg/kg q12h. Oral: 200-300 mg q12h (weight-based).",
        "dosing_peds": "Weight- and age-based dosing per specialist protocol; pediatric dosing differs meaningfully from adult per kg.",
        "dosing_renal": "IV formulation accumulates cyclodextrin vehicle — avoid IV if CrCl <50 (use oral instead); no oral dose adjustment needed for renal impairment.",
        "pharmacist_notes": "🚨 Therapeutic drug monitoring strongly recommended (highly variable, nonlinear pharmacokinetics with major CYP2C19 genetic variability). Extensive CYP450 interactions — screen every regimen.",
    },
    "amphotericin_b": {
        "generic": "Amphotericin B (Liposomal)", "brand": "AmBisome",
        "drug_class": "Polyene Antifungal",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Binds ergosterol in the fungal cell membrane, creating pores that disrupt membrane integrity (fungicidal). Broadest-spectrum systemic antifungal.",
        "spectrum": "✅ Broadest antifungal spectrum: Candida, Aspergillus, Cryptococcus, Mucormycosis/Zygomycetes, endemic fungi, Leishmania (antiparasitic use). ❌ Some intrinsically resistant species (e.g., Candida lusitaniae, Aspergillus terreus — variable).",
        "coverage": ["Fungal"],
        "indications": "Invasive/life-threatening fungal infections (especially mucormycosis, where it's first-line), empiric therapy in febrile neutropenia, cryptococcal meningitis induction, visceral leishmaniasis.",
        "side_effects": "🚨 Nephrotoxicity (significantly reduced with liposomal formulation vs. conventional deoxycholate), infusion reactions (fever, rigors, hypotension — premedicate), electrolyte wasting (potassium, magnesium).",
        "pregnancy": "Category B. Considered relatively safe in pregnancy when systemic antifungal therapy is needed (preferred over azoles for serious infection in pregnancy).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV only (negligible oral absorption).",
        "max_duration": "Per indication — mucormycosis/invasive aspergillosis often require weeks of therapy.",
        "dosing_adults": "Liposomal: 3-5 mg/kg IV once daily (up to 10 mg/kg for mucormycosis/CNS infections, per ID guidance).",
        "dosing_peds": "3-5 mg/kg IV once daily (similar to adult weight-based dosing).",
        "dosing_renal": "No dose adjustment needed for the liposomal formulation (unlike conventional deoxycholate); monitor renal function and electrolytes regardless.",
        "pharmacist_notes": "🚨 Confirm which formulation is ordered — liposomal (AmBisome), lipid complex (Abelcet), and conventional deoxycholate are dosed very differently and are NOT interchangeable mg-for-mg. Pre-hydrate and monitor electrolytes/renal function closely.",
    },
    "caspofungin": {
        "generic": "Caspofungin", "brand": "Cancidas",
        "drug_class": "Echinocandin Antifungal",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Inhibits (1,3)-beta-D-glucan synthase, disrupting fungal cell wall synthesis (fungicidal against Candida, fungistatic against Aspergillus).",
        "spectrum": "✅ Candida (incl. many azole-resistant species and C. krusei/glabrata), Aspergillus (salvage/combination therapy). ❌ Cryptococcus, Mucormycosis (no activity).",
        "coverage": ["Fungal"],
        "indications": "Invasive candidiasis/candidemia (often first-line empiric choice, especially in neutropenic or critically ill patients), esophageal candidiasis, empiric antifungal therapy in febrile neutropenia, salvage therapy for invasive aspergillosis.",
        "side_effects": "Infusion reactions, elevated LFTs, GI upset — generally well tolerated relative to amphotericin B.",
        "pregnancy": "Category C.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV only.",
        "max_duration": "Candidemia: 2 weeks after first negative blood culture and resolution of symptoms/neutropenia.",
        "dosing_adults": "Loading dose 70 mg IV day 1, then 50 mg IV once daily (increase to 70 mg/day in patients >80 kg or with an inadequate response).",
        "dosing_peds": "70 mg/m² IV loading, then 50 mg/m² once daily (max 70 mg/day).",
        "dosing_renal": "No adjustment needed for renal impairment.",
        "pharmacist_notes": "✅ Well-tolerated first-line option for candidemia in many institutional protocols; dose reduction required in moderate hepatic impairment (Child-Pugh 7-9) — 35 mg/day maintenance after standard loading dose.",
    },
    "nystatin": {
        "generic": "Nystatin", "brand": "Mycostatin",
        "drug_class": "Polyene Antifungal (topical/oral non-absorbed)",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Binds ergosterol in the fungal cell membrane, disrupting membrane integrity (fungicidal/fungistatic) — used topically/orally as it is not systemically absorbed.",
        "spectrum": "✅ Candida species (local/mucosal infections only — not absorbed, so no systemic activity).",
        "coverage": ["Fungal"],
        "indications": "Oral thrush (oral suspension, swish and swallow or spit), cutaneous candidiasis (topical cream/ointment), prophylaxis against oral/GI candidiasis in high-risk patients (e.g., ICU, prolonged antibiotics).",
        "side_effects": "GI upset (mild, with oral suspension), local irritation (topical) — very well tolerated given lack of systemic absorption.",
        "pregnancy": "Category B/C (sources vary) — topical/oral use generally considered low risk given negligible systemic absorption.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Not systemically absorbed (topical/oral local action only) — cannot be used for invasive/systemic candidiasis.",
        "max_duration": "Oral thrush: 7-14 days or until 48 hours after symptom resolution.",
        "dosing_adults": "Oral suspension: 400,000-600,000 units (4-6 mL) swish and swallow/spit qid.",
        "dosing_peds": "Infants: 100,000-200,000 units (1-2 mL) to each side of the mouth qid.",
        "dosing_renal": "No adjustment needed (not systemically absorbed).",
        "pharmacist_notes": "✅ Not effective for systemic/invasive candidiasis — confirm the clinical picture matches a local/mucosal infection before selecting nystatin over a systemic azole/echinocandin.",
    },
    "terbinafine": {
        "generic": "Terbinafine", "brand": "Lamisil",
        "drug_class": "Allylamine Antifungal",
        "aware": "Not AWaRe-classified (antifungal — WHO AWaRe covers antibacterials only)",
        "mechanism": "Inhibits squalene epoxidase, blocking ergosterol synthesis (fungicidal against dermatophytes).",
        "spectrum": "✅ Dermatophytes (Trichophyton, Microsporum, Epidermophyton) — drug of choice for onychomycosis and most tinea infections. ⚠️ Limited Candida activity.",
        "coverage": ["Fungal"],
        "indications": "Onychomycosis (oral, first-line), tinea corporis/cruris/pedis/capitis (oral or topical depending on site/severity).",
        "side_effects": "GI upset, headache, taste/smell disturbance (can be persistent), rare hepatotoxicity (baseline/periodic LFTs recommended for oral courses).",
        "pregnancy": "Category B. Oral use typically deferred until after delivery given onychomycosis is not urgent.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~40% (well absorbed, highly lipophilic — accumulates in skin/nails/fat).",
        "max_duration": "Onychomycosis: 6 weeks (fingernails) to 12 weeks (toenails). Tinea corporis: 1-2 weeks.",
        "dosing_adults": "Oral: 250 mg once daily. Topical: apply to affected area once or twice daily for 1-4 weeks depending on site.",
        "dosing_peds": "Weight-based oral dosing (≥4 years, per product labeling) for tinea capitis; topical for other tinea infections.",
        "dosing_renal": "CrCl <50: avoid oral use (insufficient data) — consider topical alternative.",
        "pharmacist_notes": "✅ Obtain baseline LFTs before starting oral therapy for onychomycosis given the multi-week/month duration; taste disturbance can persist after stopping and should be discussed with patients in advance.",
    },
    "acyclovir": {
        "generic": "Acyclovir", "brand": "Zovirax",
        "drug_class": "Antiviral (Nucleoside Analog)",
        "aware": "Not AWaRe-classified (antiviral — WHO AWaRe covers antibacterials only)",
        "mechanism": "Guanosine analog; requires viral thymidine kinase for activation, then inhibits viral DNA polymerase (virustatic, not virucidal).",
        "spectrum": "✅ Herpes simplex virus (HSV-1, HSV-2), Varicella-zoster virus (VZV). ❌ CMV, EBV (limited/no clinically useful activity).",
        "coverage": ["Herpesviruses"],
        "indications": "HSV (genital/oral, encephalitis, keratitis), VZV (chickenpox, shingles), HSV suppression in immunocompromised patients.",
        "side_effects": "Nephrotoxicity (crystalline nephropathy — ensure adequate hydration with IV use), neurotoxicity (confusion, tremor — especially in renal impairment/elderly), phlebitis at IV site.",
        "pregnancy": "Category B. Considered safe and is used for HSV/VZV treatment in pregnancy.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~15-30% (poor — valacyclovir preferred when oral bioavailability matters). IV: 100%.",
        "max_duration": "Genital herpes (recurrence): 5 days. Encephalitis: 14-21 days. Shingles: 7-10 days.",
        "dosing_adults": "Oral: 400 mg tid (HSV) or 800 mg 5x/day (VZV). IV: 5-12.5 mg/kg q8h depending on indication.",
        "dosing_peds": "IV: 10-20 mg/kg/dose q8h depending on indication and age.",
        "dosing_renal": "Requires renal-function-based dose/interval adjustment for both oral and IV — consult a dosing reference for exact adjustment at each CrCl tier.",
        "pharmacist_notes": "🚨 Ensure adequate IV hydration and infuse over at least 1 hour to reduce crystalline nephropathy risk. Not to be confused with valacyclovir (prodrug, better oral bioavailability, different dosing).",
    },
    "valacyclovir": {
        "generic": "Valacyclovir", "brand": "Valtrex",
        "drug_class": "Antiviral (Nucleoside Analog Prodrug)",
        "aware": "Not AWaRe-classified (antiviral — WHO AWaRe covers antibacterials only)",
        "mechanism": "Prodrug of acyclovir — rapidly converted to acyclovir after oral absorption, then inhibits viral DNA polymerase (virustatic).",
        "spectrum": "✅ HSV-1, HSV-2, VZV — same spectrum as acyclovir, but with much better oral bioavailability allowing less frequent dosing.",
        "coverage": ["Herpesviruses"],
        "indications": "Genital herpes (treatment/suppression), oral herpes (cold sores), herpes zoster (shingles) — oral therapy preferred over acyclovir when compliance/dosing frequency matters.",
        "side_effects": "Headache, nausea, rare thrombotic microangiopathy at very high doses (mainly seen in HIV/transplant patients on high-dose regimens), nephrotoxicity at high doses without adequate hydration.",
        "pregnancy": "Category B. Considered safe and commonly used for HSV suppression late in pregnancy to reduce neonatal transmission risk.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~55% (3-5x better than acyclovir — allows less frequent dosing for equivalent exposure).",
        "max_duration": "Genital herpes (recurrence): 3 days. Shingles: 7 days. Suppression: can be long-term/indefinite.",
        "dosing_adults": "Genital herpes recurrence: 500 mg PO bid x3 days. Shingles: 1 g PO tid x7 days. Suppression: 500-1000 mg PO once daily.",
        "dosing_peds": "≥12 years for cold sores/genital herpes per weight-based labeling; specialist-guided for younger children.",
        "dosing_renal": "Requires dose/interval adjustment based on CrCl — consult a dosing reference for exact adjustment at each tier, especially at high (shingles) doses.",
        "pharmacist_notes": "✅ Preferred over oral acyclovir when practical due to markedly better bioavailability and less frequent dosing — improves adherence for suppressive therapy.",
    },
    "oseltamivir": {
        "generic": "Oseltamivir", "brand": "Tamiflu",
        "drug_class": "Antiviral (Neuraminidase Inhibitor)",
        "aware": "Not AWaRe-classified (antiviral — WHO AWaRe covers antibacterials only)",
        "mechanism": "Inhibits influenza viral neuraminidase, preventing release of new virions from infected cells (reduces viral spread/shedding).",
        "spectrum": "✅ Influenza A and B (does not treat bacterial superinfection or other respiratory viruses).",
        "coverage": ["Influenza"],
        "indications": "Influenza treatment (most effective if started within 48 hours of symptom onset), post-exposure prophylaxis in high-risk contacts.",
        "side_effects": "Nausea/vomiting (common — take with food), headache, rare neuropsychiatric events (reported mainly in pediatric/adolescent patients, primarily in Japan).",
        "pregnancy": "Category C. Considered the preferred influenza antiviral in pregnancy per CDC — benefit is thought to outweigh risk given influenza's severity in pregnancy.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: ~75% (as the active metabolite, after rapid hepatic/GI esterase conversion from the oseltamivir prodrug).",
        "max_duration": "Treatment: 5 days. Prophylaxis: 7-10 days (up to 6 weeks during an outbreak, per public health guidance).",
        "dosing_adults": "75 mg PO bid x5 days (treatment) OR 75 mg PO once daily (prophylaxis).",
        "dosing_peds": "Weight-based dosing for children <1 year and by weight band ≥1 year — consult current CDC/product dosing table.",
        "dosing_renal": "CrCl 30-60: reduce to 30 mg bid (treatment). CrCl 10-30: 30 mg once daily. Consult current guidance for hemodialysis dosing.",
        "pharmacist_notes": "✅ Most effective when started within 48 hours of symptom onset — do not delay awaiting confirmatory testing in high-risk patients if influenza is clinically suspected during an active season.",
    },
    "albendazole": {
        "generic": "Albendazole", "brand": "Albenza",
        "drug_class": "Antiparasitic (Benzimidazole)",
        "aware": "Not AWaRe-classified (antiparasitic — WHO AWaRe covers antibacterials only)",
        "mechanism": "Binds parasitic beta-tubulin, inhibiting microtubule polymerization and glucose uptake in helminths (larvicidal/ovicidal).",
        "spectrum": "✅ Broad anthelmintic activity: intestinal nematodes (Ascaris, hookworm, whipworm, pinworm, Strongyloides), tissue parasites (Echinococcus, neurocysticercosis).",
        "coverage": ["Helminths"],
        "indications": "Soil-transmitted helminth infections (ascariasis, hookworm, whipworm), pinworm, hydatid disease (Echinococcus), neurocysticercosis (with corticosteroids/anticonvulsants as needed).",
        "side_effects": "GI upset, headache, reversible alopecia (with prolonged high-dose courses), hepatotoxicity/bone marrow suppression with prolonged therapy (monitor LFTs/CBC for courses >1 cycle).",
        "pregnancy": "Category C (D per some sources for systemic helminth-directed use) — generally avoided in the 1st trimester; WHO permits use in mass deworming programs after the 1st trimester.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: poor/variable (~5%), significantly enhanced with a fatty meal (important for systemic indications like hydatid disease/neurocysticercosis).",
        "max_duration": "Single-dose for most intestinal parasites. Hydatid disease/neurocysticercosis: weeks (multiple cycles).",
        "dosing_adults": "Intestinal parasites: 400 mg PO single dose (repeat in 2 weeks for some infections). Systemic (hydatid/neurocysticercosis): 400 mg PO bid for cycles of 28 days, weight-based for <60 kg.",
        "dosing_peds": ">2 years: same dosing as adults for intestinal parasites (400 mg single dose); weight-based for systemic indications.",
        "dosing_renal": "No adjustment typically needed.",
        "pharmacist_notes": "✅ Take with a fatty meal when treating systemic/tissue infections (hydatid disease, neurocysticercosis) to substantially improve absorption — this matters much less for luminal-only intestinal parasite treatment.",
    },
    "ivermectin": {
        "generic": "Ivermectin", "brand": "Stromectol",
        "drug_class": "Antiparasitic (Avermectin)",
        "aware": "Not AWaRe-classified (antiparasitic — WHO AWaRe covers antibacterials only)",
        "mechanism": "Binds glutamate-gated chloride channels in parasitic nerve/muscle cells, causing paralysis and death of the parasite (does not cross the mammalian blood-brain barrier at normal doses).",
        "spectrum": "✅ Strongyloidiasis (drug of choice), scabies, pediculosis (head lice), onchocerciasis, some other filarial/nematode infections.",
        "coverage": ["Helminths", "Ectoparasites"],
        "indications": "Strongyloidiasis (incl. hyperinfection syndrome), scabies (oral, for crusted/refractory or outbreak scenarios), head lice (oral, for treatment-resistant cases), onchocerciasis.",
        "side_effects": "GI upset, dizziness, pruritus (can worsen transiently as parasites die — Mazzotti-like reaction in onchocerciasis), rare hepatotoxicity.",
        "pregnancy": "Category C. Generally avoided in pregnancy unless benefit clearly outweighs risk (limited safety data).",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "Oral: well absorbed (exact bioavailability variable), enhanced with food.",
        "max_duration": "Single dose to 2 doses (1-2 weeks apart) for most indications.",
        "dosing_adults": "150-200 mcg/kg PO single dose (repeat in 2 weeks for scabies/lice; 1-2 doses for strongyloidiasis, more for hyperinfection per ID guidance).",
        "dosing_peds": "Same weight-based dosing as adults, typically restricted to children ≥15 kg (data limited below this weight).",
        "dosing_renal": "No adjustment typically needed.",
        "pharmacist_notes": "✅ Take on an empty stomach with water per product labeling (though food can enhance absorption — follow local protocol). For crusted (Norwegian) scabies, multiple doses over 1-2 weeks combined with topical permethrin is typically needed.",
    },
    "teicoplanin": {
        "generic": "Teicoplanin", "brand": "Targocid",
        "drug_class": "Glycopeptide",
        "aware": "Watch",
        "mechanism": "Glycopeptide; inhibits bacterial cell wall synthesis by binding the D-Ala-D-Ala terminus of peptidoglycan precursors (bactericidal) — mechanistically similar to vancomycin.",
        "spectrum": "✅ Gram-positive, including MRSA, coagulase-negative Staph, Enterococcus (non-VRE), Strep. ❌ Gram-negative, atypicals.",
        "coverage": ["Gram-positive", "MRSA"],
        "indications": "MRSA/Gram-positive infections where vancomycin is not tolerated or IV access/monitoring logistics favor teicoplanin's once-daily IM/IV dosing (widely used outside the US; not FDA-approved in the US).",
        "side_effects": "Infusion reactions (generally milder/less \"red man syndrome\" risk than vancomycin), nephrotoxicity (lower risk than vancomycin per most comparative data), ototoxicity, thrombocytopenia at high doses.",
        "pregnancy": "Category B3 (Australian classification) / limited human data overall.",
        "cross_allergy": "No cross-reactivity with PCN.",
        "bioavailability": "IV/IM only (not orally absorbed).",
        "max_duration": "Per indication and clinical response, similar durations to vancomycin for equivalent infections.",
        "dosing_adults": "Loading dose 6-12 mg/kg q12h for 3-5 doses, then 6-12 mg/kg once daily maintenance (higher end for severe infections e.g. endocarditis).",
        "dosing_peds": "Similar weight-based loading/maintenance principle as adults, per specialist protocol.",
        "dosing_renal": "No adjustment needed for the first 4 loading doses; reduce maintenance frequency/dose based on CrCl thereafter (e.g., every other day if CrCl 10-30, further reduction if CrCl <10).",
        "pharmacist_notes": "✅ Can be given IM (unlike vancomycin), which is useful for outpatient parenteral therapy; not FDA-approved/available in the US — check local formulary availability. Therapeutic drug monitoring recommended for serious infections.",
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
    "pen-vee k": "penicillin_vk",
    "penicillin vk": "penicillin_vk",
    "unasyn": "ampicillin_sulbactam",
    "augmentin": "amoxicillin_clavulanate",
    "keflex": "cephalexin",
    "ancef": "cefazolin",
    "maxipime": "cefepime",
    "fortaz": "ceftazidime",
    "merrem": "meropenem",
    "invanz": "ertapenem",
    "levaquin": "levofloxacin",
    "macrobid": "nitrofurantoin",
    "macrodantin": "nitrofurantoin",
    "cubicin": "daptomycin",
    "azactam": "aztreonam",
    "rifadin": "rifampin",
    "pfizerpen": "penicillin_g",
    "principen": "ampicillin",
    "nafcil": "nafcillin",
    "dynapen": "dicloxacillin",
    "ceftin": "cefuroxime",
    "zinacef": "cefuroxime",
    "claforan": "cefotaxime",
    "vantin": "cefpodoxime",
    "omnicef": "cefdinir",
    "suprax": "cefixime",
    "teflaro": "ceftaroline",
    "primaxin": "imipenem_cilastatin",
    "avelox": "moxifloxacin",
    "floxin": "ofloxacin",
    "biaxin": "clarithromycin",
    "erythrocin": "erythromycin",
    "tygacil": "tigecycline",
    "minocin": "minocycline",
    "coly-mycin m": "colistin",
    "coly-mycin": "colistin",
    "chloromycetin": "chloramphenicol",
    "monurol": "fosfomycin",
    "amikin": "amikacin",
    "nebcin": "tobramycin",
    "inh": "isoniazid",
    "myambutol": "ethambutol",
    "pza": "pyrazinamide",
    "diflucan": "fluconazole",
    "sporanox": "itraconazole",
    "vfend": "voriconazole",
    "ambisome": "amphotericin_b",
    "cancidas": "caspofungin",
    "mycostatin": "nystatin",
    "lamisil": "terbinafine",
    "zovirax": "acyclovir",
    "valtrex": "valacyclovir",
    "tamiflu": "oseltamivir",
    "albenza": "albendazole",
    "stromectol": "ivermectin",
    "targocid": "teicoplanin",
}

ALL_CLASSES = sorted({d["drug_class"] for d in ANTIMICROBIALS.values()})
ALL_COVERAGE = sorted({tag for d in ANTIMICROBIALS.values() for tag in d["coverage"]})
KEY_BY_LABEL = {f"{d['generic']} ({d['brand']})": k for k, d in ANTIMICROBIALS.items()}

# WHO AWaRe (Access/Watch/Reserve) classification. "Access"/"Watch"/"Reserve" are the three
# canonical categories from WHO's AWaRe antibiotic list (https://aware.essentialmeds.org/).
# A handful of agents (e.g. rifampin here) aren't part of WHO's general bacterial-infection
# AWaRe list and carry an explanatory string instead — aware_category() normalizes that to
# a clean "Not classified" state everywhere it's displayed or filtered on.
AWARE_TONE = {"Access": "green", "Watch": "yellow", "Reserve": "red"}


def aware_category(data):
    val = data.get("aware", "")
    return val if val in AWARE_TONE else None


ALL_AWARE = ["Access", "Watch", "Reserve"]

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
# INSTITUTIONAL EMPIRIC-REGIMEN SCENARIOS
# Transcribed from an institutional antimicrobial guideline document (2nd
# edition, produced by a hospital's antibiotic stewardship subcommittee),
# Chapter 1: Empiric Antibiotic Regimens. This is ONE institution's local
# protocol — it reflects their antibiogram and formulary, not a universal
# standard. `pages` on each category cites the source page numbers so a
# reader can verify every row against the original document directly.
# Restricted/controlled-antibiotic status is that institution's own
# formulary policy, separate from the WHO AWaRe classification used
# elsewhere in this app.
# ---------------------------------------------------------------------------
GUIDELINE_SOURCE = "()"

RESTRICTED_ANTIBIOTICS = [
    "Fosfomycin IV", "Tigecycline", "Linezolid IV/PO", "Caspofungin", "Remdesivir",
    "Tocilizumab", "Ceftazidime/avibactam", "Daptomycin", "Ceftaroline",
]
CONTROLLED_ANTIBIOTICS = ["Colistin", "Minocycline", "Chloramphenicol"]

EMPIRIC_REGIMEN_SCENARIOS = {
    "Skin and Soft Tissue Infections": {
        "pages": "11-13",
        "scenarios": [
            {"indication": "Skin abscess, boils, and furuncles",
             "first_line": "Doxycycline 100 mg PO bid OR TMP-SMX 1 DS PO bid (2 DS tabs if BMI > 40)",
             "alternative": "Clindamycin 300-450 mg PO tid"},
            {"indication": "Cellulitis/erysipelas — facial",
             "first_line": "Vancomycin IV 15-20 mg/kg q8-12h",
             "alternative": "Linezolid* 600 mg PO/IV q12h"},
            {"indication": "Cellulitis/erysipelas — extremities",
             "first_line": "Outpatient: Cephalexin 500 mg q8h. Inpatient: Cefazolin OR ceftriaxone 2 g once daily.",
             "alternative": "Outpatient: Cephalexin 500 mg PO qid. Inpatient: Vancomycin IV 15-20 mg/kg q8-12h (ID consult) or Linezolid* 600 mg IV/PO bid."},
            {"indication": "Cellulitis/erysipelas — diabetes mellitus",
             "first_line": "Early/mild, outpatient: TMP-SMX 1-2 DS PO bid + Cephalexin 500 mg PO qid. Hospitalized/severe: Imipenem/cilastatin 500 mg q6h + vancomycin 15-20 mg/kg q8-12h.",
             "alternative": "Early/outpatient: Minocycline* + amoxicillin. Hospitalized/severe: Imipenem/cilastatin 500 mg q6h + linezolid* 600 mg IV/PO bid OR meropenem 1 g q8h + linezolid* 600 mg IV/PO bid."},
            {"indication": "Impetigo",
             "first_line": "Few lesions/bullous: Mupirocin ointment 2% bid x5 days. Many lesions/bullous: TMP-SMX 1 DS PO bid.",
             "alternative": "Clindamycin 300-600 mg PO q8h"},
            {"indication": "Diabetic foot ulcer",
             "first_line": "Superficial: TMP-SMX 1 DS PO bid. Deeper ulcers: TMP-SMX 1 DS PO bid + either imipenem/cilastatin 500 mg q6h or vancomycin 15-20 mg/kg q8-12h. Ulcers with systemic toxicity: Piperacillin-tazobactam 4.5 g q6-8h + amikacin 15 mg/kg once daily + either daptomycin* 4.5-6 mg/kg once daily or linezolid* 600 mg bid.",
             "alternative": "Superficial: Doxycycline 100 mg bid PO. Deeper ulcers: Minocycline* 100 mg PO bid. Ulcers with systemic toxicity: Piperacillin-tazobactam 4.5 g q6-8h + amikacin 15 mg/kg once daily + cefazoline* 600 mg bid."},
            {"indication": "Necrotizing fasciitis / gas gangrene",
             "first_line": "Imipenem/cilastatin 500-900 mg IV q6h + clindamycin 600-900 mg q8h + vancomycin 15-20 mg/kg q8-12h",
             "alternative": "Piperacillin-tazobactam 4.5 g q6-8h + amikacin 15 mg/kg once daily + linezolid* 600 mg bid"},
            {"indication": "Pyomyositis",
             "first_line": "Vancomycin 15-20 mg/kg q8-12h",
             "alternative": "Cefazoline* 600 mg bid"},
            {"indication": "Hidradenitis suppurativa (dermatology consult)",
             "first_line": "Stage 1 (local wound care): Clindamycin 1% lotion bid for localized disease without sinus tracts/scarring. Stage 2: Clindamycin 300 mg PO bid + rifampin 300 mg bid, both for 10-12 weeks. Stage 3: cyclosporine 2-6 mg/kg once daily x 4-15 months.",
             "alternative": ""},
            {"indication": "Infected decubitus / venous / arterial insufficiency ulcer",
             "first_line": "Mild cases: local wound care. Moderate-severe cases: Oral doxycycline 100 mg bid PO + TMP-SMX 1 DS bid PO, OR IV piperacillin-tazobactam 4.5 g q8h + vancomycin 15-20 mg/kg q8-12h (surgical debridement with deep soft-tissue wound-margin cultures).",
             "alternative": "Imipenem/cilastatin 500 mg IV q6h + vancomycin 15-20 mg/kg q8-12h"},
            {"indication": "Rat / human / cat bite",
             "first_line": "Amoxicillin/clavulanic acid 1 g PO bid",
             "alternative": "Doxycycline 100 mg bid PO OR TMP-SMX 1 DS bid PO, + clindamycin 300 mg bid PO"},
            {"indication": "Phlebitis",
             "first_line": "Doxycycline 100 mg bid PO",
             "alternative": "Doxycycline 100 mg bid PO"},
        ],
    },
    "Bone and Joint Infections": {
        "pages": "14",
        "scenarios": [
            {"indication": "Acute osteomyelitis (adults) — while awaiting tissue/blood cultures",
             "first_line": "Vancomycin 15-20 mg/kg q12h + ceftriaxone 2 g once daily",
             "alternative": "Clindamycin 600-900 mg qthly IV + ceftriaxone 2 g once daily",
             "notes": "Chronic osteomyelitis: base antibiotics on deep tissue/bone culture."},
            {"indication": "Acute septic arthritis — monoarticular",
             "first_line": "Without STD risk: vancomycin 15-20 mg/kg q12h + cefazoline 2 g once daily. With STD risk: vancomycin 15-20 mg/kg q12h + ceftriaxone 2 g once daily.",
             "alternative": "Without STD risk: vancomycin 15-20 mg/kg q12h + doxycycline 100 mg bid (7 days for gram-positive cocci on gram stain)."},
            {"indication": "Acute septic arthritis — polyarticular",
             "first_line": "Piperacillin-tazobactam 4.5 g q6-8h + vancomycin 15-20 mg/kg q12h",
             "alternative": "Imipenem 500 mg q6h + vancomycin 1 g once daily"},
            {"indication": "Prosthetic joint, post-op or post intra-articular injection/penetrating injury",
             "first_line": "Vancomycin 15-20 mg/kg q12h",
             "alternative": "Vancomycin 600-900 mg qthly IV"},
            {"indication": "Septic bursitis",
             "first_line": "Vancomycin 15-20 mg/kg q12h",
             "alternative": ""},
        ],
        "notes": "Antibiotics should be based on the deep tissue/bone culture. In acute Monoarticular septic arthritis, vancomycin infusion should be guided by gram stain.",
    },
    "Cardiovascular System Infections": {
        "pages": "15",
        "scenarios": [
            {"indication": "Native valve endocarditis — while awaiting cultures",
             "first_line": "Vancomycin 15-20 mg/kg q8-12h + ceftriaxone 2 g q24h OR gentamicin 1 mg/kg q8hrly IV/IM",
             "alternative": "Daptomycin* 8-12 mg/kg IV q24h (or q48hrly if CrCl<30ml/min) as a substitute for vancomycin"},
            {"indication": "Prosthetic valve infection",
             "first_line": "Vancomycin 15-20 mg/kg q8-12h + gentamicin 1 mg/kg q8hrly + rifampin 300 mg IV/IM/PO q8hly",
             "alternative": ""},
        ],
        "notes": "Empiric therapy should cover methicillin-susceptible and -resistant staphylococci, streptococci, and enterococci. In MRSA bacteremia, vancomycin is usually preferred; reserve daptomycin for β-lactam hypersensitivity or intolerance. ID and surgery consult must be taken. MIC values must be determined before starting therapy with penicillins (MIC ≤0.12 mcg/mL). Draw two sets of blood cultures.",
    },
    "Gastrointestinal Tract Infections": {
        "pages": "16",
        "scenarios": [
            {"indication": "Neutropenic enterocolitis, typhlitis",
             "first_line": "Bowel rest (consider TPN). Imipenem/cilastatin 500 mg q6hrly",
             "alternative": "Piperacillin/tazobactam 4.5 g q6hrly"},
            {"indication": "Watery diarrhea",
             "first_line": "Antimicrobial therapy is not typically indicated for acute watery diarrhea, as most cases resolve spontaneously.",
             "alternative": ""},
            {"indication": "Dysentery — severe cases/high risk",
             "first_line": "Ceftriaxone + ciprofloxacin",
             "alternative": "Severe/high risk: azithromycin"},
            {"indication": "Cholera",
             "first_line": "Doxycycline 300 mg as a single dose",
             "alternative": "Azithromycin as a single dose"},
            {"indication": "Enteric fever",
             "first_line": "See the dedicated Enteric Fever guideline elsewhere in the source document (§9.6).",
             "alternative": ""},
        ],
        "notes": "Empiric treatment for amebic dysentery is not routinely warranted unless trophozoites are visualized on stool microscopy. High risk = immunocompromised or infection due to E. histolytica.",
    },
    "Hepatobiliary Tract Infections": {
        "pages": "17",
        "scenarios": [
            {"indication": "Acute cholecystitis — non-life-threatening",
             "first_line": "Piperacillin/tazobactam 4.5 g q6hrly OR imipenem/clastatin 500 mg q6hrly",
             "alternative": "Ceftriaxone 1-2 g once daily + metronidazole 500 mg q8hrly IV"},
            {"indication": "Acute cholecystitis — life-threatening",
             "first_line": "Imipenem/cilastatin 500 mg q6hrly",
             "alternative": "Ertapenem 1 g once daily IV/meropenem 1 g q8hrly"},
            {"indication": "Biliary sepsis/CBD obstruction/cholangitis; spontaneous bacterial peritonitis (SBP); secondary peritonitis (polymicrobial/mono-microbial post-op perforation); pancreatitis abscess/infected pseudocyst or acute pancreatitis with necrosis",
             "first_line": "Piperacillin/tazobactam 4.5 g q6hrly",
             "alternative": "Metronidazole 500-750 mg q8hrly for 7-10 days + imipenem/cilastatin 500 mg q6hrly OR piperacillin/tazobactam 4.5 g q8hrly"},
            {"indication": "Liver abscess",
             "first_line": "Metronidazole 500-750 mg q8hrly + imipenem/cilastatin 500 mg q6hrly",
             "alternative": "Ertapenem 1 g once daily"},
            {"indication": "Acute pancreatitis (without necrosis)",
             "first_line": "No antibiotics recommended",
             "alternative": ""},
            {"indication": "Diverticulitis / perirectal abscess / peritonitis",
             "first_line": "Inpatient, mild-moderate disease: no antibiotics recommended. Severe, life-threatening: piperacillin/tazobactam 4.5 g q6hrly.",
             "alternative": "Imipenem/cilastatin 500 mg q6hrly"},
        ],
    },
    "Genitourinary Tract Infections": {
        "pages": "18-19",
        "scenarios": [
            {"indication": "Cystitis — male",
             "first_line": "Nitrofurantoin 50-100 mg PO qid * 3-5 days",
             "alternative": "Fosfomycin* 3 g PO stat dose"},
            {"indication": "Cystitis — female",
             "first_line": "Nitrofurantoin 50-100 mg PO qid * 3-5 days",
             "alternative": "Fosfomycin* 3 g PO stat dose"},
            {"indication": "Acute pyelonephritis",
             "first_line": "Imipenem 500 mg IV q6hrly OR ertapenem 1 g once daily",
             "alternative": "Fosfomycin* 12-24 g IV q6-8hrly"},
            {"indication": "Critical illness / sepsis / urinary tract obstruction",
             "first_line": "Add vancomycin 15-20 mg/kg q12-8hrly with or without loading dose (to cover MRSA)",
             "alternative": ""},
            {"indication": "Catheter-associated UTI (CA-UTI)",
             "first_line": "Same as sepsis/pyelonephritis above",
             "alternative": "Meropenem 1 g q8hrly"},
            {"indication": "Perinephric abscess",
             "first_line": "Piperacillin/tazobactam 4.5 g q6-8hrly",
             "alternative": ""},
            {"indication": "Asymptomatic bacteriuria",
             "first_line": "Do not treat, except in pregnancy, low birth-weight neonates, and prior to GU procedures",
             "alternative": ""},
            {"indication": "Acute prostatitis (pending cultures)",
             "first_line": "Fosfomycin oral 48hrly for 4-6 weeks",
             "alternative": "Minocycline* OR trimethoprim-sulfamethoxazole 1 DS tablet bid"},
            {"indication": "Epididymo-orchitis / urethritis / cervicitis",
             "first_line": "Ceftriaxone 1 g IM x1 dose + doxycycline 100 mg PO bid for 10 days",
             "alternative": "Ceftriaxone 1 g IM* + azithromycin 1 g PO stat dose, OR azithromycin 2 g stat dose"},
            {"indication": "Syphilis — primary/secondary, early latent",
             "first_line": "Benzathine penicillin G 2.4 MIU IM stat dose",
             "alternative": "Ceftriaxone 2 g IV Qd for 10-14 days"},
            {"indication": "Syphilis — late latent",
             "first_line": "Benzathine penicillin G 2.4 MIU IM q week x 3 weeks = 7.2 MIU total dose",
             "alternative": "There is no published data on efficacy of alternatives."},
            {"indication": "Neurosyphilis",
             "first_line": "Penicillin G 3-4 MIU IV q4h x 10-14 days",
             "alternative": "Ceftriaxone* 1-2 g (IV or IM) q24h x 10-14 days"},
        ],
    },
    "Obstetrics and Gynecological Infections": {
        "pages": "20",
        "scenarios": [
            {"indication": "Endometritis / septic pelvic phlebitis (postpartum)",
             "first_line": "Ceftriaxone 1 g Qd + metronidazole 500 mg q8hrly OR clindamycin 900 mg q8hrly + gentamicin 5 mg/kg once daily IV q8hrly",
             "alternative": "Piperacillin/tazobactam 4.5 g q8hrly"},
            {"indication": "PID / salpingitis / tubo-ovarian abscess",
             "first_line": "Outpatient: ceftriaxone 500 mg IM stat dose + doxycycline 100 mg PO bid (100 mg orally every 12 hours). Inpatient: ceftriaxone 500 mg IV stat dose + metronidazole 500 mg PO bid (500 mg PO plus metronidazole 500 mg IV every 12 hours).",
             "alternative": ""},
            {"indication": "Septic abortion",
             "first_line": "Piperacillin/tazobactam 4.5 g q8hrly",
             "alternative": "Imipenem/cilastatin 500 mg q6hrly"},
            {"indication": "Candida vaginitis",
             "first_line": "Clotrimazole cream/vaginal pessaries",
             "alternative": "Fluconazole 150 mg single dose"},
        ],
        "notes": "Also inform the neonatal team if the mother has endometritis. For PID in in-patients, switch from IV to oral when the patient is afebrile. In case of tubo-ovarian abscess, use either clindamycin or metronidazole to complete 14 days of therapy along with doxycycline (in addition to the regimen provided).",
    },
    "Upper Respiratory Tract Infections": {
        "pages": "21-22",
        "scenarios": [
            {"indication": "Acute sinusitis < 10 days",
             "first_line": "Usually symptomatic care — no antibiotics needed.",
             "alternative": ""},
            {"indication": "Acute sinusitis > 10 days, toxic, facial pain, or increased CRP",
             "first_line": "Amoxicillin-clavulanate 500/125 mg PO tid or 875/125 mg PO bid for 5-7 days",
             "alternative": "Clindamycin 300 mg qid or 450 mg tid for 5-7 days OR cefuroxime/cefpodoxime"},
            {"indication": "Chronic sinusitis > 3 months",
             "first_line": "Amoxicillin-clavulanate 500/125 mg PO tid or 875/125 mg PO bid for 5-7 days",
             "alternative": "Doxycycline 100 mg PO bid OR 200 mg qd"},
            {"indication": "Sinusitis (intubation-associated)",
             "first_line": "Imipenem/cilastatin 500 mg q6hrly ± vancomycin 15-20 mg/kg q12h",
             "alternative": "Piperacillin/tazobactam 4.5 g q8hrly"},
            {"indication": "Acute pharyngitis",
             "first_line": "Amoxicillin",
             "alternative": "Clindamycin OR cephalexin",
             "notes": "Add vancomycin if risk of MRSA. Peritonsillar/lateral pharyngeal abscess requires treatment even if viral etiology is distinguished from bacterial pharyngitis; oral ulcers, cough, and hoarseness make bacterial cause less likely."},
            {"indication": "Vincent's angina (anaerobes)",
             "first_line": "Amoxicillin + metronidazole",
             "alternative": "Clindamycin 300 mg qid or 450 mg tid"},
            {"indication": "Parapharyngeal space infection",
             "first_line": "Ceftriaxone + metronidazole",
             "alternative": "Levofloxacin + clindamycin"},
            {"indication": "Peritonsillar abscess",
             "first_line": "Piperacillin/tazobactam",
             "alternative": "Cefuroxime + metronidazole"},
            {"indication": "Jugular vein septic phlebitis",
             "first_line": "Same as above",
             "alternative": "Same as above"},
            {"indication": "Parotitis (adults), hot/tender",
             "first_line": "No MRSA risk & immunocompetent: cephalexin + metronidazole. MRSA risk & immunocompromised: piperacillin/tazobactam + vancomycin.",
             "alternative": "No MRSA risk & immunocompetent: clindamycin. MRSA risk & immunocompromised: imipenem + linezolid*."},
        ],
    },
    "Lower Respiratory Tract Infections": {
        "pages": "23-24",
        "scenarios": [
            {"indication": "Viral tracheobronchitis",
             "first_line": "For most patients, the risks associated with antibiotic use outweigh the benefits — supportive care.",
             "alternative": ""},
            {"indication": "Nosocomial tracheobronchitis (tracheostomy/intubation-associated), based on gram stain",
             "first_line": "Gram-positive: add vancomycin 15-20 mg/kg q8-12h. Gram-negative rods: add piperacillin/tazobactam 4.5 g q6hrly.",
             "alternative": "Gram-positive: add linezolid* 600 mg bid. Gram-negative rods: add imipenem/cilastatin 500 mg q6hrly."},
            {"indication": "Community-acquired pneumonia (CAP) — outpatient",
             "first_line": "No co-morbids: amoxicillin 1 g tid PO. Co-morbids: amoxicillin/clavulanic acid 250-750 mg PO bid + clarithromycin 500 mg bid.",
             "alternative": "No co-morbids: doxycycline 100 mg bid PO. Co-morbids: levofloxacin 500-750 mg PO once daily."},
            {"indication": "Community-acquired pneumonia (CAP) — inpatient, non-ICU",
             "first_line": "Ceftriaxone 1-2 g once daily + doxycycline 100 mg bid",
             "alternative": "Cefuroxime 1-2 g IV q12h + azithromycin IV 500 mg once daily for a minimum of 3 days"},
            {"indication": "Community-acquired pneumonia (CAP) — inpatient, ICU",
             "first_line": "Ceftriaxone 1-2 g once daily + clarithromycin 500 mg bid",
             "alternative": "Moxifloxacin 400 mg IV q24h"},
            {"indication": "Hospital-acquired / ventilator-associated pneumonia (HAP/VAP)",
             "first_line": "See the dedicated HAP/VAP guideline elsewhere in the source document (§9.1).",
             "alternative": "",
             "notes": "Clindamycin no longer recommended due to increased resistance; do not initiate therapy in mild exacerbation without risk factors."},
            {"indication": "Lung abscess",
             "first_line": "Meropenem 1 g q8hrly",
             "alternative": "Clindamycin IV 600 mg q8hrly followed by 300 mg PO qid"},
            {"indication": "Acute empyema (community-acquired)",
             "first_line": "Ceftriaxone 1 g once daily + metronidazole IV 500 mg q8hrly*",
             "alternative": "Meropenem 1 g q8hrly plus vancomycin 15-20 mg/kg q8-12h"},
            {"indication": "Empyema (hospital-acquired / post-procedural)",
             "first_line": "Piperacillin/tazobactam 4.5 g q6hrly; treat according to cultures",
             "alternative": "No risk factors for Pseudomonas: levofloxacin 750 mg IV/PO q24h. Risk factors for Pseudomonas: piperacillin/tazobactam 4.5 g q6hrly."},
            {"indication": "Chronic/subacute empyema",
             "first_line": "",
             "alternative": ""},
            {"indication": "Acute bacterial exacerbation of COPD (severe) / bronchiectasis",
             "first_line": "Piperacillin/tazobactam 4.5 g q6hrly",
             "alternative": ""},
            {"indication": "Cystic fibrosis",
             "first_line": "Piperacillin/tazobactam 4.5 g q6hrly",
             "alternative": ""},
        ],
    },
    "Eye Infections": {
        "pages": "25",
        "scenarios": [
            {"indication": "Orbital cellulitis",
             "first_line": "Vancomycin 15-20 mg/kg q8-12h + ceftriaxone 2 g IV q24h + metronidazole 1 g IV q12h",
             "alternative": "Vancomycin 15-20 mg/kg q8-12h + piperacillin/tazobactam 4.5 g IV q8hrly"},
            {"indication": "Dacryocystitis — severe infection",
             "first_line": "Vancomycin* 15-20 mg/kg q8-12h + ceftriaxone 2 g IV q24h",
             "alternative": "For mild infection: amoxicillin-clavulanate (500 mg/125 mg PO tid or 875 mg/125 mg PO bid) for 7-10 days"},
            {"indication": "Endophthalmitis (hematogenous)",
             "first_line": "Intravitreal vancomycin 1 mg in 0.1 mL + ceftazidime 2.25 mg in 0.1 mL",
             "alternative": "For mild infection: clindamycin 300 mg qid or 450 mg tid"},
            {"indication": "Cavernous sinus thrombosis",
             "first_line": "Vancomycin 15-20 mg/kg q12h + ceftriaxone 2 g IV q24h ± metronidazole 500 mg IV q8hrly (if increased risk of anaerobic infection/dental source)",
             "alternative": ""},
            {"indication": "Toxoplasmosis",
             "first_line": "TMP-SMX 10 mg/kg/day (trimethoprim component) IV/PO q12h x 6 weeks",
             "alternative": "Can substitute vancomycin with cefazolin in cases of suspicion of MRSA. Can substitute ceftriaxone with levofloxacin in penicillin-allergic patients."},
        ],
    },
    "Ear Infections": {
        "pages": "26",
        "scenarios": [
            {"indication": "Malignant otitis externa",
             "first_line": "Ciprofloxacin 400 mg IV q8hrly (or if very early infection, 750 mg PO q8-12h)",
             "alternative": "Piperacillin/tazobactam 4.5 g q8hrly"},
            {"indication": "Pediatric otitis media",
             "first_line": "Amoxicillin high dose 80-90 mg/kg/day PO divided q12-8hrly",
             "alternative": "Amoxicillin-clavulanate extra-strength oral suspension 90/6.4 mg/kg/day q12h"},
            {"indication": "Acute mastoiditis",
             "first_line": "Vancomycin: child 40-60 mg/kg IV divided 2-4 times a day; adult 15-20 mg/kg IV q8-12h. PLUS piperacillin/tazobactam: child 300 mg/kg/day in 4 divided doses (max 16 g); adult 4.5 g IV q8hrly.",
             "alternative": "Vancomycin: child 40-60 mg/kg IV divided 2-4 times a day; adult 15-20 mg/kg IV q8-12h. PLUS ceftazidime: child 50 mg/kg IV q8hrly; adult 2 g IV q8hrly."},
            {"indication": "Chronic mastoiditis (surgery often required)",
             "first_line": "Based on cultures",
             "alternative": ""},
        ],
        "notes": "In malignant otitis externa, P. aeruginosa is the causative agent in >95% of cases. Acute mastoiditis patients are usually too ill for outpatient therapy. ENT consultation required.",
    },
    "CNS Infections": {
        "pages": "27",
        "scenarios": [
            {"indication": "Bacterial meningitis — preterm to age < 1 month",
             "first_line": "Ampicillin 75-100 mg/kg IV q8-12h + cefotaxime 100-150 mg/kg/day in divided doses q8-12h OR gentamicin 2.5 mg/kg IV q8-12h",
             "alternative": "Meropenem 2g qthly + vancomycin 45-60 mg/kg/day IV divided q6-8hrly, dexamethasone 0.15mg/kg IV q6-8hrly * 2-4 days administered with or just before the 1st dose of antibiotic"},
            {"indication": "Bacterial meningitis — 1 month to 50 years",
             "first_line": "Ceftriaxone 2 g q12hrly + vancomycin 15-20 mg/kg IV q8-12h + dexamethasone 0.15 mg/kg IV q6hrly x2-4 days (1st dose 15-20 min prior to or concomitant with the 1st dose of antibiotics)",
             "alternative": "Ampicillin 2 g IV q4h + meropenem 2 g IV q8hrly + vancomycin 15-20 mg/kg IV q8-12h + dexamethasone 0.15 mg/kg IV q6-12hrly x2-4 days prior to or concomitant with 1st dose of antibiotics"},
            {"indication": "Bacterial meningitis — > 50 years",
             "first_line": "Ampicillin 2 g IV q4h + ceftriaxone 2 g q12hrly + vancomycin 15-20 mg/kg IV q8-12h + dexamethasone 0.15 mg/kg IV q6hrly x2-4 days, prior to or concomitant with 1st dose of antibiotic",
             "alternative": ""},
            {"indication": "Viral encephalitis",
             "first_line": "Acyclovir 5-12.5 mg/kg IV q8hrly",
             "alternative": ""},
            {"indication": "Cryptococcal meningitis",
             "first_line": "Induction phase: amphotericin B 0.7-1 mg/kg IV q24h + flucytosine 400-600 mg PO once daily for 8 weeks. Consolidation phase: fluconazole 400-800 mg PO once daily. Maintenance phase: fluconazole 200 mg PO once daily for 12 months.",
             "alternative": "",
             "notes": "For details, refer to the meningitis guidelines section elsewhere in the source document."},
        ],
    },
}

# ---------------------------------------------------------------------------
# CHAPTER 4: TREATMENT FOR MISCELLANEOUS INFECTIONS (Viral / Fungal / Parasitic)
# Same source and same "first-line / alternative" shape as EMPIRIC_REGIMEN_SCENARIOS
# above, so it's rendered with the same render_scenario_card() helper.
# Source pages 55-64.
# ---------------------------------------------------------------------------
MISC_INFECTIONS = {
    "Viral Infections": {
        "pages": "55-56",
        "scenarios": [
            {"indication": "Crimean-Congo Hemorrhagic Fever",
             "first_line": "Ribavirin 30 mg/kg PO initial dose, then 15 mg/kg PO q6hrly x4 days, then 7.5 mg/kg PO q6hrly x6 days"},
            {"indication": "CMV retinitis",
             "first_line": "Immediate sight-threatening lesions: Ganciclovir (intravitreal injection 2 mg/injection) + valganciclovir 900 mg PO bid x14-21 days, then 900 mg PO once daily. Peripheral lesions: Valganciclovir 900 mg PO bid x14-21 days, then 900 mg PO once daily. Post-treatment suppression: Valganciclovir 900 mg PO once daily — discontinue once CD4 >100 for 6 months.",
             "alternative": "Ganciclovir 5 mg/kg IV q12h x14-21 days, then 900 mg PO once daily, with transition to valganciclovir 900 mg PO q24h"},
            {"indication": "CMV colitis",
             "first_line": "Ganciclovir 5 mg/kg IV q12h with transition to valganciclovir 900 mg PO q12hrly following clinical improvement (duration individualized, usually 3-6 weeks)"},
            {"indication": "Bell's palsy (HSV)",
             "first_line": "Prednisolone 1 mg/kg PO divided bid, tapered over next 5 days + IV acyclovir 10 mg/kg/dose every 8 hours OR oral acyclovir 1600-2400 mg PO daily, for 10 days"},
            {"indication": "Encephalitis (HSV)",
             "first_line": "IV Acyclovir 10-12.5 mg/kg/dose q8hrly for 14-21 days"},
            {"indication": "Primary genital herpes",
             "first_line": "PO Acyclovir 400 mg tid x7-10 days"},
            {"indication": "Oro-labial herpes (fever blisters)",
             "first_line": "PO Acyclovir 400 mg 5 times/day x5 days",
             "alternative": "Acyclovir ointment 5%"},
            {"indication": "Genital herpes — episodic recurrences (HSV)",
             "first_line": "PO Acyclovir 800 mg tid x2 days OR 400 mg PO tid x5 days"},
            {"indication": "Chickenpox (VZV)",
             "first_line": "Immunocompetent host, mild disease: no treatment. Immunocompromised, moderate disease: Acyclovir 800 mg PO 5 times per day. Immunocompromised, severe disease: IV Acyclovir 10 mg/kg infused over 1 hour q8hrly x7 days."},
            {"indication": "Zoster / Shingles (VZV)",
             "first_line": "Mild to moderate: Acyclovir 800 mg PO 5 times a day x7-14 days. Severe (ocular or neurologic/disseminated disease): Acyclovir 10 mg/kg/dose IV every 8 hours."},
        ],
    },
    "Fungal Infections": {
        "pages": "57-60",
        "notes": "This table reads dense in the source PDF — dosing shown here is a best-effort transcription; verify against the original before use, especially the weight/renal-based invasive candidiasis and aspergillosis regimens.",
        "scenarios": [
            {"indication": "Allergic bronchopulmonary aspergillosis",
             "first_line": "Corticosteroids + itraconazole 200 mg capsules PO q12hrly",
             "alternative": "Corticosteroids + voriconazole 200 mg PO q12hrly"},
            {"indication": "Aspergillosis — chronic cavitary/extra pulmonary",
             "first_line": "Voriconazole IV 6 mg/kg twice daily for 2 doses, then 4 mg/kg twice daily; oral 200 mg twice daily. Some experts reserve IV for severely ill patients. Duration typically ≥6 months; some patients need prolonged, potentially lifelong therapy.",
             "alternative": "Itraconazole 200 mg capsules PO q12hrly"},
            {"indication": "Aspergillosis — invasive (incl. disseminated and extrapulmonary)",
             "first_line": "Voriconazole IV 6 mg/kg twice daily for 2 doses, then 4 mg/kg twice daily; oral 200-300 mg twice daily (weight-based ~3-4 mg/kg twice daily). Duration depends on degree/duration of immunosuppression, disease site, and response — immunosuppressed patients may need more prolonged treatment.",
             "alternative": "Liposomal amphotericin B 3-5 mg/kg/day IV"},
            {"indication": "Candidemia — neutropenic patient",
             "first_line": "Caspofungin 70 mg IV loading dose, then 50 mg IV q24h",
             "alternative": "Fluconazole loading dose 800 mg (12 mg/kg), then 400 mg IV q24h"},
            {"indication": "Candidemia — non-neutropenic patient",
             "first_line": "Voriconazole IV 6 mg/kg twice daily for 2 doses, then 4 mg/kg twice daily",
             "alternative": "Amphotericin B 0.3-1 mg/kg/day as a single infusion OR caspofungin 70 mg IV loading dose day 1, then 50 mg IV once daily"},
            {"indication": "Invasive candidiasis prophylaxis (heme malignancy / HCT / solid organ transplant recipients)",
             "first_line": "ICU patients at high risk in units with a high rate (>5%) of invasive candidiasis (off-label use): nystatin 500,000 units qid until day 5-7",
             "alternative": "Fluconazole IV loading dose 800 mg (12 mg/kg) day 1, then 400 mg (6 mg/kg) IV maintenance once daily; if hemodynamically stable, fluconazole oral 400 mg (6 mg/kg) once daily"},
            {"indication": "Thrush (oropharyngeal candidiasis)",
             "first_line": "Fluconazole 200 mg IV/oral once daily",
             "alternative": "Voriconazole IV 4 mg/kg twice daily, oral 200 mg twice daily"},
            {"indication": "Esophageal candidiasis",
             "first_line": "Fluconazole 200-400 mg IV/oral once daily for 14-21 days",
             "alternative": "Voriconazole 200-400 mg oral twice daily for 14-21 days"},
            {"indication": "Urinary candidiasis",
             "first_line": "Do not treat asymptomatic patients. Treat if candidemia is suspected in a neutropenic patient, or in a patient undergoing a urologic procedure (several days before and after). Cystitis (symptomatic): fluconazole 200 mg (3 mg/kg) once daily x2 weeks. Pyelonephritis: fluconazole 200-400 mg (3-6 mg/kg) once daily x2 weeks.",
             "alternative": "Patients who do not respond after 1 week: amphotericin B once daily for 1-2 weeks"},
            {"indication": "Cutaneous candidiasis",
             "first_line": "Miconazole 2% cream bid OR clotrimazole 1% solution bid",
             "alternative": "Fluconazole 100 mg once daily in refractory cases"},
            {"indication": "Onychomycosis",
             "first_line": "Terbinafine oral 250 mg PO q24h x6 weeks",
             "alternative": "Itraconazole oral 200 mg PO q24h x3 months"},
            {"indication": "Tinea corporis, cruris, or pedis",
             "first_line": "Terbinafine 1% cream bid for 1-2 weeks",
             "alternative": "Topical clotrimazole or ketoconazole, OR fluconazole 150 mg PO once weekly x3-5 weeks"},
            {"indication": "Tinea capitis",
             "first_line": "Oral terbinafine 250 mg PO q24h x2-4 weeks",
             "alternative": "Fluconazole 150 mg/day x3-4 weeks"},
            {"indication": "Mucormycosis",
             "first_line": "Liposomal amphotericin B 5-10 mg/kg IV daily",
             "alternative": "Conventional amphotericin B 1 mg/kg/day"},
            {"indication": "Vulvovaginal candidiasis",
             "first_line": "Mild/moderate, immunocompetent: fluconazole 150 mg single dose. Severe, or immunocompromised: fluconazole 150 mg every 72h for 2-3 doses.",
             "notes": "Cultures are recommended for recurrent infections."},
        ],
    },
    "Parasitic Infections": {
        "pages": "61-64",
        "notes": "Malaria dosing (weight-based Artemether-lumefantrine schedule + primaquine, with G6PD testing required before primaquine) is complex in the source table — treat the entry below as a starting point only and confirm exact doses against source page 64 or the linked institutional malaria guideline before treating a patient.",
        "scenarios": [
            {"indication": "Blastocystis hominis",
             "first_line": "No treatment required"},
            {"indication": "Dientamoeba fragilis",
             "first_line": "Metronidazole 750 mg PO tid x10 days"},
            {"indication": "Entamoeba histolytica (amebiasis)",
             "first_line": "Asymptomatic cyst passer: diloxanide furoate 500 mg PO tid x10 days. Mild diarrhea/dysentery: metronidazole 500-750 mg PO tid x10 days. Severe or extra-intestinal disease/hepatic abscess: metronidazole 750 mg PO tid x7-10 days.",
             "alternative": "Mild diarrhea/dysentery: tinidazole 2 g PO daily x3 days. Severe/extra-intestinal disease/hepatic abscess: tinidazole 2 g PO daily x5 days."},
            {"indication": "Giardia lamblia (giardiasis)",
             "first_line": "Tinidazole 2 g PO single dose",
             "alternative": "Metronidazole 250 mg PO tid x5-7 days OR nitazoxanide 500 mg PO bid x3 days"},
            {"indication": "Leishmaniasis",
             "first_line": "Cutaneous: most resolve spontaneously; complex disease — fluconazole 200 mg PO daily x6 weeks. Mucosal and visceral: amphotericin B 0.5-1 mg/kg IV daily or every other day to a total of 15-30 mg/kg.",
             "alternative": "Amphotericin B 1 mg/kg IV daily or every other day to a total dose of 15-20 mg/kg"},
            {"indication": "Pneumocystis jirovecii pneumonia (PCP)",
             "first_line": "TMP-SMX-DS 2 tabs PO q6hrly x21 days. Start prednisolone 15-30 minutes before therapy: 40 mg PO q12h x5 days, then 40 mg q24h for 11 days.",
             "alternative": "Clindamycin 300-450 mg PO q6hrly x21 days + primaquine 15-30 mg base PO q24h x21 days"},
            {"indication": "Ascariasis",
             "first_line": "Albendazole 400 mg PO single (stat) dose",
             "alternative": "Mebendazole 500 mg PO stat dose OR 100 mg PO bid x2 weeks"},
            {"indication": "Whipworm (Trichuris)",
             "first_line": "Albendazole 400 mg PO stat dose, repeat in 2 weeks",
             "alternative": "Mebendazole 100 mg PO bid x3 days"},
            {"indication": "Pinworm (Enterobius)",
             "first_line": "Albendazole 400 mg PO stat dose",
             "alternative": "Mebendazole 100 mg PO bid x3 days"},
            {"indication": "Hookworm",
             "first_line": "Albendazole 400 mg PO daily x3 days",
             "alternative": "Mebendazole 100 mg PO bid x3 days"},
            {"indication": "Strongyloidiasis",
             "first_line": "Asymptomatic or intestinal disease: ivermectin 200 mcg/kg/day PO x1-2 days. Disseminated/hyperinfection with sepsis or meningitis: ivermectin 200 mcg/kg/day PO until stool/sputum exams are negative.",
             "alternative": "Asymptomatic/intestinal disease: albendazole 400 mg PO bid x7 days. No listed alternative for disseminated/hyperinfection."},
            {"indication": "Tapeworm — systemic (Echinococcus)",
             "first_line": "Albendazole: <60 kg 400 mg PO bid; ≥60 kg 15 mg/kg/day in 2 divided doses. Duration depends on severity, site, and response — usually 3-6 months."},
            {"indication": "Tapeworm — intestinal",
             "first_line": "Niclosamide 2 g PO once (stat)",
             "alternative": "Nitazoxanide"},
            {"indication": "Pediculosis (head lice)",
             "first_line": "Permethrin 5% lotion, applied to dry hair, left on 10 minutes (failure to respond may indicate drug resistance)",
             "alternative": "Ivermectin (oral) 150-200 mcg/kg as a single dose"},
            {"indication": "Scabies",
             "first_line": "Permethrin 5% lotion applied to entire skin from chin to toes, including under fingernails/toenails (may require up to 30 g); leave on 8-14 hours; repeat in 1-2 weeks",
             "alternative": "Ivermectin (oral) 150-200 mcg/kg as a single dose"},
            {"indication": "Malaria — uncomplicated, P. falciparum or unknown species",
             "first_line": "Weight-based 3-day Artemether-lumefantrine schedule (dosed at hour 0, hour 8, then twice daily on days 2-3); for P. vivax/P. ovale, add primaquine (check G6PD status first) after completing schizonticidal therapy.",
             "notes": "See source PDF page 64 (and the referenced institutional malaria guideline PDF) for the exact weight-based tablet counts and primaquine regimen — do not use the summary above alone to dose a patient."},
            {"indication": "Dengue",
             "first_line": "No specific antimicrobial first-line regimen listed — supportive management per WHO dengue guidelines.",
             "notes": "Refer to detailed institutional/WHO dengue guidelines."},
        ],
    },
}

# ---------------------------------------------------------------------------
# CHAPTER 6: SAFETY AND DOSING IN SPECIAL POPULATIONS
# Reference tables transcribed from source pages 76-97. Rendered as pandas
# DataFrames via st.dataframe(). As with the rest of this institutional
# guideline content, treat this as a first-draft transcription and verify
# specific numbers (especially dialysis/CRRT dosing) against the source PDF.
# ---------------------------------------------------------------------------
PREG_LACT_ROWS = [
    ("Acyclovir", "B", "Compatible", "Yes", "1.83% to 3.65%"),
    ("Amikacin", "D", "Compatible", "Yes", "N/A"),
    ("Amoxicillin", "B", "Compatible", "Yes", "N/A"),
    ("Amoxicillin/clavulanic acid", "B", "Compatible", "Yes", "0.02% to 0.07%"),
    ("Amphotericin B", "B", "Unsafe", "Not known", "N/A"),
    ("Ampicillin", "B", "Compatible (WHO)", "Yes", "N/A"),
    ("Azithromycin", "B", "Caution advised", "Yes", "N/A"),
    ("Cefazolin", "B", "Compatible", "Yes", "<1%"),
    ("Cefixime", "B", "Unknown", "Yes", "N/A"),
    ("Cefotaxime", "B", "Compatible", "Yes", "N/A"),
    ("Cefpodoxime", "B", "Caution advised", "Yes", "N/A"),
    ("Ceftazidime", "B", "Compatible", "Yes", "N/A"),
    ("Ceftazidime/avibactam", "-", "-", "Ceftazidime: Yes; Avibactam: Not known", "N/A"),
    ("Ceftriaxone", "B", "Compatible", "Yes", "N/A"),
    ("Cephalexin", "B", "Safe", "Yes", "<1%"),
    ("Chloramphenicol", "C", "Unsafe", "Yes", "N/A"),
    ("Ciprofloxacin", "C", "Compatible", "Yes", "2.8%"),
    ("Clarithromycin", "C", "Caution advised", "Yes", "<1%"),
    ("Clindamycin", "B", "Compatible", "Yes", "1.2% to 4.7%"),
    ("Colistin", "C", "Caution advised", "Yes", "N/A"),
    ("Doxycycline", "D", "Unsafe", "Yes", "N/A"),
    ("Minocycline", "D", "Unsafe", "Yes", "N/A"),
    ("Erythromycin", "B", "Compatible", "Yes", "N/A"),
    ("Ethambutol", "Safe C", "Compatible", "Yes", "N/A"),
    ("Ethionamide", "C", "Caution advised", "Yes", "N/A"),
    ("Fluconazole", "C (single dose) / D (other regimens)", "Compatible", "Yes", "5% to 10%"),
    ("Fosfomycin IV/oral", "B", "Unknown", "Yes", "N/A"),
    ("Fusidic acid", "C (no problems reported)", "Unknown", "Yes", "N/A"),
    ("Gentamicin", "D", "Compatible", "Yes", "1.56%"),
    ("Imipenem/cilastatin", "C", "Caution advised", "Yes", "N/A"),
    ("Isoniazid", "C", "Compatible", "Yes", "N/A"),
    ("Itraconazole", "C", "Unsafe", "Yes", "N/A"),
    ("Levofloxacin", "C", "Unsafe", "Yes", "6%"),
    ("Ketoconazole", "C", "Compatible", "Yes", "1.4%"),
    ("Meropenem", "B", "Unknown", "Yes", "N/A"),
    ("Metronidazole", "B (unsafe in 1st trimester)", "Unsafe", "Yes", "Breast milk concentrations similar to maternal plasma"),
    ("Penicillin G / Penicillin G benzathine", "B", "Caution advised", "Yes", "N/A"),
    ("Piperacillin/tazobactam", "B", "Compatible", "Piperacillin present in breast milk; no data for tazobactam", "N/A"),
    ("Pyrazinamide", "C", "Caution advised", "Yes", "Breast milk concentrations lower than maternal plasma"),
    ("Ribavirin", "X", "Unsafe", "Not known", "N/A"),
    ("Rifampicin", "B", "Compatible", "Yes", "N/A"),
    ("Streptomycin", "D", "Compatible", "Yes", "N/A"),
    ("Sulfadoxine/pyrimethamine", "C", "Unsafe", "-", "N/A"),
    ("Teicoplanin", "B3 (Australia)", "Unknown", "-", "N/A"),
    ("Tobramycin", "B (ophthalmic) / D (injection)", "Caution advised", "Present in breast milk following injection", "N/A"),
    ("Tigecycline", "Fetal toxicity in animals reported", "Unknown", "Not known", "N/A"),
    ("Trimethoprim-sulfamethoxazole", "C", "Caution advised", "Yes", "N/A"),
    ("Vancomycin", "C", "Caution advised", "Yes", "N/A"),
    ("Voriconazole", "D", "Unsafe", "Not known", "N/A"),
    ("Caspofungin", "C", "Unknown", "Not known", "N/A"),
    ("Ceftaroline", "B", "Caution advised", "Not known (low concentration)", "N/A"),
    ("Daptomycin", "B", "-", "Yes (low concentration)", "N/A"),
]
PREG_LACT_COLUMNS = ["Antibiotic", "Pregnancy Category", "Lactation Status", "Excretion in Milk", "Relative Infant Dose (RID)"]
PREG_LACT_NOTES = (
    "In general, breastfeeding is considered acceptable when RID <10%. Antibiotics present in breast milk "
    "may cause non-dose-related modification of infant bowel flora — monitor infants for GI disturbances."
)

VACCINE_PREG_ROWS = [
    ("BCG", "Live attenuated", "Safe", "C", "Avoid during pregnancy"),
    ("Tdap", "Toxoid and antigen", "Unknown", "C", "See note below"),
    ("Td", "Toxoid", "Caution advised", "-", "Indicated in 2nd and 3rd trimester"),
    ("Hepatitis B", "Surface antigen", "Unknown", "C", "Indicated in Hep B carriers"),
    ("H. influenzae type B", "Polysaccharide", "Unknown", "C", "See note below"),
    ("Polio vaccine", "Live", "Safe", "C", "Indicated in women at high risk needing immediate protection"),
    ("MMR", "Live attenuated", "Safe", "C", "Contraindicated in pregnancy"),
    ("Varicella", "Live attenuated", "Safe", "Unknown", "Women exposed to chickenpox in first 20 weeks or near term should receive varicella IgG"),
    ("Pneumococcal", "Polysaccharide and conjugated", "Caution advised", "C", "See note below"),
    ("Hepatitis A", "Inactivated Hep A virus", "Unknown", "C", "Give hepatitis A IgG within first week of exposure"),
    ("Influenza vaccine", "Inactivated", "Unknown", "B", "See note below"),
    ("Meningococcal", "Polysaccharide", "Safe", "MSV: C, MCV: B", "See note below"),
    ("Tetanus toxoid", "Toxoid", "Caution advised", "-", "See Td"),
    ("Tuberculin", "Purified protein derivative", "Safe", "C", "CDC considers it safe"),
    ("Rabies", "Inactivated", "Safe", "C", "Can be given as post-exposure prophylaxis"),
    ("Measles", "Live attenuated", "Safe", "C", "Contraindicated in pregnancy"),
    ("Typhoid", "Polysaccharide", "Safe", "C", "If extremely necessary, delay until 2nd or 3rd trimester"),
]
VACCINE_PREG_COLUMNS = ["Vaccine", "Type", "Lactation Status", "Pregnancy Category", "Comments"]
VACCINE_PREG_NOTES = (
    "All live vaccines are considered contraindicated during pregnancy. Pregnancy/conception should be "
    "avoided for 1 month after MMR and 3 months after varicella vaccination. \"See note below\" entries "
    "are not routinely indicated in pregnancy but can be given for certain indications other than primary "
    "immunization. FDA pregnancy categories: A = controlled studies show no risk; B = animal studies show "
    "no risk (no adequate human studies) or animal studies show risk not confirmed in human studies; "
    "C = risk cannot be ruled out; D = evidence of fetal risk, but benefit may outweigh risk; "
    "X = contraindicated in pregnancy."
)

DIALYSIS_ROWS = [
    ("Ampicillin", "1-2 g IV q12hrly (give dialysis-day dose after dialysis)", "500 mg-1 g IV q12hrly", "1-2 g IV q8-12hrly", ""),
    ("Amoxicillin/clavulanate (oral)", "250-500 mg (amoxicillin component) q24h + extra dose after dialysis", "No data", "No data", ""),
    ("Amoxicillin/clavulanate (IV)", "Adult: 1000/200 mg initial dose, then 500/100 mg q24h (+ extra dose on dialysis days). Child <40 kg: 25/5 mg per kg q24h (+12.5/2.5 mg per kg after dialysis).", "No data", "No data", ""),
    ("Amikacin", "7.5 mg/kg q48hrly; give an extra 50% of the normal renal-function dose (3.75 mg/kg) after dialysis", "Intermittent: 2 mg/kg added to one exchange per day (min. dwell 6h). Continuous: add to all exchanges — loading 25 mg, maintenance 12 mg/L.", "7.5 mg/kg q24h; follow serum trough levels", ""),
    ("Acyclovir (oral)", "Usual dose 200 mg 5x/day or 400 mg q12hrly → give 200 mg q12hrly. Usual dose 800 mg 5x/day → loading 400 mg then maintenance 200 mg after each dialysis session.", "Usual dose 200 mg 5x/day or q12hrly → 200 mg q12hrly. Usual dose 800 mg 5x/day → loading 400 mg + maintenance 200 mg q12hrly.", "200 mg q12hrly", ""),
    ("Acyclovir (IV)", "2.5-5 mg/kg/dose q24h; administer after dialysis on dialysis days", "2.5-5 mg/kg/dose q24h; no supplemental dose needed", "5-10 mg/kg/dose q12-24h", ""),
    ("Cefazolin", "0.5-1 g after dialysis, OR 2 g after if next dialysis expected within 48h, OR 3 g after if next dialysis expected within 72h", "500 mg q12h or 1 g q24h", "2 g loading dose, then 1 g q8h or 2 g q12h", ""),
    ("Cefixime", "300 mg once daily", "200 mg once daily", "No data available; use of an alternative agent recommended", ""),
    ("Ceftazidime", "IV 500 mg-1 g q24h; administer after hemodialysis on dialysis days", "IV 1 g q24h", "IV 2 g q8-12h", "Dialyzable (55-85% with low-flux filters)"),
    ("Ceftazidime/avibactam", "0.94 g q24h (0.94 g q48h if minimal residual kidney function/less severe infection); give after hemodialysis on dialysis days", "0.94 g q24h (0.94 g q48h if minimal residual kidney function/less severe infection)", "1.25 g q8h", "Dialyzable (~57% ceftazidime, ~55% avibactam)"),
    ("Ceftriaxone", "Poorly dialyzed — no dosage adjustment necessary. Use >2 g/day has not been studied; monitor closely, especially with concurrent hepatic dysfunction.", "-", "-", ""),
    ("Cefotaxime", "Usual dose 1-2 g q6-8hrly → 1-2 g q24h. Usual dose 1 g q6hrly → 1-2 g q12hrly.", "0.5-1 g q24h", "1-2 g q8-12h", ""),
    ("Ciprofloxacin", "Oral 250-500 mg q24h (XR cystitis 500 mg q24h; XR comp. UTI/pyelo 500 mg q24h); IV 200-400 mg q24h", "Same as dialysis regimen", "Same as dialysis regimen", "Give dialysis-day dose after dialysis"),
    ("Ertapenem", "0.5 g IV q24h (dose for CrCl <10 mL/min); if dosed <6h before HD, give 150 mg supplemental dose after dialysis", "0.5 g IV q24h", "0.5 g IV q24h", ""),
    ("Gentamicin", "Give the normal renal-function dose plus an extra ~50% on dialysis days, dosed after dialysis; periodically check peak/trough levels", "1.7-2.0 mg/kg q48hrly", "1.7-2.0 mg/kg q24hrly", "Periodically check peak and trough serum levels"),
    ("Itraconazole (oral solution)", "100 mg q12-24h", "100 mg q12-24h", "100-200 mg q12h", ""),
    ("Levofloxacin", "Starting dose 250 mg once daily → 250 mg q48hrly. Starting dose 500 mg once daily → 250 mg q48hrly or 125 mg once daily. Starting dose 750 mg once daily → 500 mg q48h or 250 mg once daily.", "Same as dialysis regimen", "Starting dose 750 mg once daily → 500 mg q48h or 250 mg once daily", ""),
    ("Meropenem", "0.5 g IV q24h", "-", "1 g q12h", ""),
    ("Metronidazole", "Dose for CrCl <10 mL/min: 7.5 mg/kg q12hrly; give one dose after dialysis on dialysis days", "7.5 mg/kg q12hrly", "7.5 mg/kg q6hrly", ""),
    ("Oseltamivir", "Treatment: 30 mg immediately, then 30 mg after each dialysis session for 5 days. Seasonal treatment: 75 mg immediately as a single dose (provides 5-day duration). Seasonal prophylaxis: 30 mg immediately, then 30 mg once weekly for the recommended duration.", "Same regimen as dialysis", "Same regimen as dialysis", ""),
    ("Piperacillin/tazobactam", "IV 4.5 g q12h or 2.25 g q8h; dosing after dialysis on dialysis days preferred but not required", "IV 4.5 g q12h or 2.25 g q8h", "IV 4.5 g q8h, or loading dose 2.25 g then 4.5 g q6h", "Dialyzable (~6% piperacillin, ~21% tazobactam)"),
    ("Colistin", "Loading dose IV 300 mg CBA (9 MIU), then 150-200 mg CBA (4.5-6 MIU) once daily as maintenance starting 24h after loading dose; on non-dialysis days give baseline 130 mg CBA (2 MIU) q12hrly, add 40-50 mg (1.5 MIU) after dialysis", "Loading dose 300 mg CBA (9 MIU), then 220 mg CBA (6.6 MIU) q12hrly as maintenance", "Loading dose 300 mg CBA (9 MIU), then 150-200 mg CBA (4.5-6 MIU) once daily starting 12h after loading dose", ""),
    ("Pyrazinamide", "CrCl <30 mL/min, drug-susceptible TB (oral): 40-55 kg 1 g 3x/week; 56-75 kg 1.5 g 3x/week; 76-90 kg 2 g 3x/week. Drug-resistant TB (alternative agent): 25-40 mg/kg 3x/week.", "Dialyzable (~15% of total clearance); limited PK data — dose as for CrCl <30 mL/min", "No CRRT data available; no dosage adjustment thought necessary, but pyrazinamide is somewhat dialyzed by CRRT — monitor closely for response and hepatotoxicity", ""),
    ("Vancomycin", "CrCl <15 mL/min: loading dose 20-25 mg/kg, then maintenance 10-15 mg/kg q48-72h", "Loading dose 20-25 mg/kg; obtain a level ~48-72h after loading dose and dose subsequent doses (usually 10-15 mg/kg) to attain goal concentrations", "Loading dose 20-25 mg/kg, then 7.5-10 mg/kg q12h with more frequent trough monitoring", ""),
    ("Daptomycin", "CrCl <30 mL/min: usual recommended dose q48h (doses >8 mg/kg not well studied — monitor closely)", "Follow CrCl <30 mL/min dosing recommendations", "6 mg/kg q24h", ""),
    ("Ceftaroline", "Usual dose 600 mg bid → 200 mg q12h. Usual dose 600 mg q8hrly → 200 mg q8h.", "Same as dialysis regimen", "Usual dose 600 mg q12h → 400 mg q8h. Usual dose 600 mg q8h → 400 mg q8h.", ""),
]
DIALYSIS_COLUMNS = ["Antibiotic", "Hemodialysis", "CAPD", "CRRT", "Comments"]
DIALYSIS_NOTES = (
    "Where literature supports that a drug is removed by dialysis but exact dosing information is not "
    "available, the usual method for CAPD is 2 L exchanged qid (8 L/day): 8 L x 20 mg lost per L = 160 mg "
    "supplemented per day. Drugs not listed in this table should be given at their routine renally-adjusted "
    "dose, preferably after dialysis — supplemental doses are not generally required in that case."
)

HEPATIC_ADJUSTMENT = {
    "Antibacterial": ["Ceftriaxone", "Chloramphenicol", "Clindamycin", "Fusidic acid", "Isoniazid", "Rifampicin", "Metronidazole", "Tigecycline", "Tinidazole"],
    "Antifungal": ["Itraconazole", "Voriconazole", "Caspofungin"],
    "Antiviral": ["Antiretrovirals"],
}

CSF_PENETRATION = {
    "Therapeutic concentration in CSF without inflammation": ["Chloramphenicol", "Isoniazid", "Metronidazole", "Rifampicin", "Sulfonamides"],
    "Therapeutic concentration in CSF with inflammation": ["Acyclovir", "Ampicillin", "Cefotaxime", "Ciprofloxacin", "Ceftazidime", "Ceftriaxone", "Imipenem", "Meropenem", "Penicillin G (high dose)", "Piperacillin/tazobactam", "Vancomycin"],
    "Sub-therapeutic with or without inflammation": ["Amikacin", "Amphotericin B", "Cefazolin", "Clindamycin", "Gentamicin", "Itraconazole", "Polymyxin B/colistin", "Streptomycin"],
}
CSF_NOTES = (
    "Ciprofloxacin concentration is not adequate for streptococci. Avoid imipenem for meningitis therapy "
    "due to seizure potential. This table does not apply to penicillin-resistant S. pneumoniae."
)

LONGTERM_LABS_ROWS = [
    ("Acyclovir", "Hydration status and urine output; urinalysis; serum creatinine; liver enzymes; CBC; signs/symptoms of neurotoxicity; neutrophil count at least twice weekly in neonates receiving acyclovir 60 mg/kg/day IV; monitor infusion site"),
    ("Aminoglycosides", "Urinalysis; creatinine; appropriately timed trough concentrations; weight; intake and output; hearing assessment"),
    ("Amphotericin B", "Creatinine; electrolytes (especially potassium and magnesium); signs/symptoms of infusion-related reactions (fever, shaking chills, hypotension, anorexia, nausea, vomiting, headache, tachypnea)"),
    ("Clindamycin", "Observe for diarrhea; monitor for colitis and resolution of symptoms; in severe liver disease, monitor liver function tests periodically"),
    ("Fluconazole / Itraconazole / Voriconazole", "Periodic LFTs (AST, ALT, alkaline phosphatase), especially in patients with signs or pre-existing liver disease"),
    ("Linezolid", "Weekly CBC, particularly in patients at increased risk of bleeding (pre-existing myelosuppression, concomitant marrow-suppressing medications, >2 weeks of therapy, chronic infection with prior/concomitant antibiotic therapy); peripheral sensory and visual function with extended therapy (≥3 months); new-onset neuropathic or visual symptoms regardless of duration; lactic acid in patients with renal dysfunction; monitor for serotonin syndrome / neuroleptic-malignant-like reaction (especially with concomitant serotonergic agents or carcinoid syndrome); monitor for hyponatremia/SIADH"),
    ("Penicillins, cephalosporins, carbapenems", "Comprehensive metabolic profile and CBC every two weeks"),
    ("Rifampin", "Baseline LFTs (AST, ALT, bilirubin); creatinine; CBC every 2-4 weeks during therapy, monitoring liver function in patients with pre-existing hepatic impairment and periodic monitoring of serum creatinine and CBC in patients with baseline abnormalities; monitor for symptoms of interstitial lung disease/pneumonitis"),
    ("Trimethoprim/sulfamethoxazole", "CBC, electrolytes, renal function"),
    ("Vancomycin", "Creatinine, CBC, and vancomycin trough weekly"),
]
LONGTERM_LABS_COLUMNS = ["Antibiotic", "Suggested Labs / Monitoring Parameters"]
LONGTERM_LABS_NOTES = (
    "This list covers the minimum labs suggested for a patient on a prolonged antibiotic course and is "
    "based in part on published IDSA recommendations. Additional labs may be requested at the provider's "
    "discretion; other, less common antimicrobials may also require monitoring not listed here."
)

ADULT_DOSES_ROWS = [
    ("Acyclovir IV", "5-12.5 mg/kg IV q8hrly", "750 mg and 500 mg compounding bags", "Hematologic: decreased hemoglobin (neonates 13%), decreased absolute neutrophil count (neonates 3-16%); Nervous system: malaise (oral 12%); Nephrotoxicity"),
    ("Acyclovir oral", "400 mg q8hrly (HSV); 800 mg 5 times/day (VZV)", "Acylex 200 mg, 400 mg tablets; Acylex suspension 200 mg/5 mL", "Headaches; increased liver enzymes"),
    ("Albendazole oral", "200-400 mg q12-24hrly", "Zentel suspension 200 mg/5 mL; Zentel 200 mg tablet", "Headaches; increased liver enzymes"),
    ("Amikacin injection", "7.5 mg/kg q12hrly OR 15 mg/kg q24hrly", "Grasil injection 500 mg, 250 mg, 100 mg", "Neurotoxicity (incl. muscle twitching, seizure, numbness, tingling of skin); auditory/vestibular ototoxicity; nephrotoxicity; respiratory paralysis"),
    ("Ampicillin injection", "1-2 g q4-6hrly", "Ampicillin 500 mg", "Brain disease (penicillin-induced), glossitis, seizures, sore mouth"),
    ("Amphotericin B injection (standard prep.)", "0.3-1 mg/kg/day once daily", "Amphotericin compounding bag 30 mg, 50 mg", "Infusion reactions; electrolyte abnormalities; nephrotoxicity"),
    ("Caspofungin injection", "Loading dose 70 mg q24h, maintenance dose 50 mg q24h", "Caspofungin compounding bag 50 mg, 70 mg", "Infusion reactions; electrolyte abnormalities; tachycardia and hypotension"),
    ("Amoxicillin/clavulanic acid oral", "625 mg tid or 1 g bid", "Augmentin tablets 375 mg, 625 mg, 1 g; Augmentin suspension 312.5 mg, 156.25 mg, 457 mg", "C. difficile-associated diarrhea; cholestatic hepatitis; hypersensitivity reactions; candidiasis"),
    ("Amoxicillin/clavulanic acid IV", "1.2 g q8hrly", "Calamox 600 mg, 1.2 g", "Same as oral formulation"),
    ("Gentamicin injection", "2 mg/kg loading, then 1.7-2 mg/kg q8hrly OR 5.1 mg/kg q24hrly (7 mg/kg if critically ill)", "Genticyn 20 mg, 40 mg, 80 mg", "Nephrotoxicity; neuromuscular blockade and respiratory paralysis; ototoxicity; hearing impairment"),
    ("Imipenem injection", "500 mg q6hrly or 1 g q8hrly", "Imipenem/cilastatin compounding bag 250 mg/500 mg, 500 mg", "Decreased hematocrit (infants and children 3 months-12 years); increased serum AST (infants and children 3 months-12 years); seizure (neonates ≤3 months: adults <1%)"),
    ("Isoniazid tablet", "5-10 mg/kg/day (max single dose 300 mg/day)", "100 mg", ">10%: hepatic — increased serum transaminases; vasculitis"),
    ("Levofloxacin injection", "250-750 mg IV/PO q24hrly", "Bexus infusion 750 mg; Leflox infusion 500 mg", "Dysglycemia; CNS toxicity; aortic aneurysm; tendinopathy"),
    ("Levofloxacin oral", "250-750 mg PO q24hrly", "Leflox tablets 250 mg, 500 mg, 750 mg", "Myasthenia gravis; pseudotumor cerebri; QTc interval prolongation"),
    ("Linezolid injection", "600 mg q12hrly", "Ecasil 600 mg, 200 mg", "Diarrhea; pancytopenia; thrombocytopenia"),
    ("Linezolid oral", "600 mg bid", "Ecasil tablets 400 mg, 600 mg; Ecasil suspension 100 mg/mL", "Same as injectable"),
    ("Mebendazole", "100 mg PO single dose or for 3 days; 500 mg PO single dose", "Vermox 100 mg, 500 mg tablets", "Abdominal pain; anorexia; diarrhea; flatulence; nausea; vomiting; hepatitis"),
    ("Meropenem injection", "1-2 g q8hrly", "Penro, meronem 1 g, 500 mg", "C. difficile-associated diarrhea; pancytopenia; CNS toxicity"),
    ("Metronidazole injection", "500-750 mg q8hrly (max 4 g/day)", "Flagyl 500 mg", "Peripheral neuropathy; aseptic meningitis; seizures; encephalopathy"),
    ("Metronidazole tablet", "500-750 mg q8hrly (max 4 g/day)", "Flagyl 400 mg tablet; Flagyl suspension 200 mg/5 mL", "Same as injectable"),
    ("Penicillin G injection", ">20 MIU/day", "Benzyl penicillin G (IV/IM) 1 MIU", "C. difficile-associated diarrhea; seizures at high doses"),
    ("Piperacillin/tazobactam", "4.5 g q6-8hrly", "Pip/tazo compounding bag 2.25 g, 4.5 g, 3.375 g; Tazzo injection 2.25 g, 4.5 g", "C. difficile-associated diarrhea; drug-induced thrombocytopenia; nephrotoxicity and neurotoxicity"),
    ("Teicoplanin injection", "6-12 mg/kg; first 3-5 doses q12hrly, then q24hrly", "Teicoplanin compounding bag 200 mg, 400 mg; Targocid injection 400 mg and 200 mg", "Hypersensitivity; marked decrease in platelets (high doses >15 mg/kg/day)"),
    ("Tigecycline injection", "Loading dose 100-200 mg; maintenance dose 50-100 mg q12hrly", "Tigecycline compounding bag 100 mg, 50 mg; Tygacil 50 mg", "Diarrhea, nausea, vomiting; increased INR, prolonged partial thromboplastin time and prothrombin time; thrombocytopenia"),
    ("Vancomycin injection", "Loading dose 1.5-2 g; maintenance dose 5-20 mg/kg q12hrly-8hrly", "Vancomycin compounding bag 1 g, 750 mg and 500 mg", "Infusion reactions; nephrotoxicity; drug-induced immune thrombocytopenia"),
    ("Daptomycin injection", "4-12 mg/kg IV q24hrly", "Dapute 350 mg", "Eosinophilic pneumonitis; myopathy and rhabdomyolysis; peripheral neuropathy"),
    ("Ceftazidime injection", "1-2 g IV/IM q8-12hrly", "Ceftazidime compounding bag 2 g, 1 g; Fortum 1 g, 250 mg and 500 mg", "Increased lactate dehydrogenase; neuromuscular excitability"),
    ("Clindamycin injection", "1.2-2.7 g/day q6hrly", "Dalacin 300 mg, 600 mg", "C. difficile-associated diarrhea"),
    ("Clindamycin oral", "150-450 mg q6-8hrly (max 1.8 g/day)", "Dalacin capsules 300 mg, 150 mg", "C. difficile-associated diarrhea"),
    ("Fosfomycin injection", "12-24 g/day", "Focin 1 g", "Diarrhea, headache, eosinophilia, nausea, neutropenia and hypokalemia; IV formulation has a large sodium load — 14.4 mEq of sodium per gram, 10g=1 litre of N.S."),
    ("Fosfomycin oral", "3 g PO single dose or every other day", "Focin 500 mg tablet; Focin suspension 250 mg/mL", "Same as injectable"),
    ("Fusidic acid oral", "500 mg tid", "Fucidin 250 mg tablet", "Nausea, vomiting, elevated bilirubin"),
    ("Azithromycin oral", "500 mg on day 1, then 250 mg once daily as per indication", "Azomax 250 mg, 500 mg tablets; Azomax suspension 200 mg/5 mL", "QTc interval prolongation; thrombocytopenia (rare)"),
    ("Azithromycin injection", "1 g single dose in C. trachomatis; 2 g single dose in N. gonorrhoeae", "Zithrax 500 mg", "Same as oral"),
    ("Cefotaxime injection", "1-2 g q4-8hrly", "Claforan 250 mg, 500 mg and 1 g", "C. diff colitis; local phlebitis; positive Coombs test"),
    ("Ceftazidime/avibactam injection", "2.5 g q8hrly", "Zavicefta 2.5 g", "C. diff colitis; local phlebitis, increased LFTs, coma"),
    ("Cefpodoxime oral", "100-400 mg q12hrly", "Orelox 100 mg", "C. diff colitis"),
    ("Ceftriaxone injection", "1-2 g q24hrly", "Ceftriaxone compounding bag 1 g, 2 g; Rocephin injection 1 g, 2 g", "Drug-induced thrombocytopenia; pseudocholelithiasis at >2 g in patients on TPN"),
    ("Chloramphenicol oral", "50-100 mg/kg/day PO/IV divided q6hrly (max 4 g/day)", "Chloramphenicol 250 mg capsules", "Thrombocytopenia; gray baby syndrome; aplastic anemia"),
    ("Ciprofloxacin injection", "200-400 mg q8-12hrly", "Ciprox 200 mg", "Dysglycemia; CNS toxicity"),
    ("Ciprofloxacin oral", "250-750 mg q12hrly", "Ciproxin 250 mg, 500 mg; Novidat suspension 125 mg/5 mL and 250 mg/5 mL", "Aortic aneurysm; tendinopathy; myasthenia gravis; pseudotumor cerebri; QTc interval prolongation"),
    ("Colistin injection", "3 MIU q8hrly, 4.5 MIU q12hrly", "Colistimethate compounding bag; Colicraft 1 MIU; Colistimethate 3 MIU", "Nephrotoxicity; neurotoxicity"),
    ("Doxycycline oral", "100 mg q12hrly", "Vibramycin 100 mg capsules", "Esophagitis; discoloration of teeth; photosensitivity"),
    ("Minocycline oral", "Loading dose 200 mg, maintenance 100-200 mg bid", "Minogen 100 mg tablet", "GIT disturbances"),
    ("Erythromycin oral", "250-500 mg q6-12hrly", "Erythrocin 250 mg, 500 mg; Erythrocin suspension 200 mg/5 mL", "Hypersensitivity; muscle weakness; anaphylaxis; GIT disturbances"),
    ("Ertapenem injection", "1-2 g once daily", "Invanz 1 g; Ertapenem compounding bag 1 g", "GIT disturbances; raised LFTs; seizure risk lower than other carbapenems"),
    ("Fluconazole injection", "Loading dose 200-400 mg, maintenance dose 100-400 mg q24hrly", "Infuderm 100 mg/50 mL", "Neutropenia; increased PT/PTT"),
    ("Fluconazole oral", "Loading dose 200-400 mg, maintenance dose 100-400 mg q24hrly", "Diflucan capsules 50 mg, 100 mg, 200 mg; Flu-z suspension 50 mg/5 mL", "Nausea, headache, skin rash"),
    ("Clarithromycin injection", "250-500 mg q12hrly", "Klaricid injection 500 mg", "GIT disturbances; increased PT/PTT"),
    ("Clarithromycin oral", "250-500 mg q12hrly", "Klaricid tablets 500 mg, 250 mg; Klaricid suspension 125 mg/5 mL", "GIT disturbances"),
    ("Moxifloxacin oral", "400 mg PO/IV q24hrly", "Avelox 400 mg tablet", "Dysglycemia; CNS toxicity; aortic aneurysm; tendinopathy"),
    ("Moxifloxacin IV", "400 mg PO/IV q24hrly", "Avelox 400 mg injection", "Myasthenia gravis; pseudotumor cerebri; QTc interval prolongation"),
]
ADULT_DOSES_COLUMNS = ["Drug", "Dose Range", "Strength (as stocked at SIH)", "Common Adverse Effects"]
ADULT_DOSES_NOTES = (
    "The dose ranges above give a general idea and doses often vary by indication — always confirm the "
    "indication-specific dose (e.g. via the Empiric Regimens or Drug Lookup pages) rather than relying on "
    "this table alone. Doses shown are for patients with normal renal function. Source references cited "
    "in the original document: Sanford Guide, UpToDate."
)

PEDS_NEONATAL_ROWS = [
    ("Meropenem", "<32 weeks PMA", "Septic dose 20 mg/kg/dose q12h; meningitis dose 40 mg/kg/dose q12h", "20-40 mg/kg/dose q8h; meningitis 120 mg/kg/day, max 6 g/day q8h"),
    ("Meropenem", "32-37 weeks PMA", "Septic dose 20 mg/kg/dose q8h; meningitis dose 40 mg/kg/dose q8h", "20-40 mg/kg/dose q8h; meningitis 120 mg/kg/day, max 6 g/day q8h"),
    ("Cephalexin", "Under 7 days", "25 mg/kg/dose q12h (max 125 mg/dose)", "25-100 mg/kg/day q6-8h"),
    ("Cephalexin", "7-21 days", "25 mg/kg/dose q8h (max 125 mg/dose)", "25-100 mg/kg/day q6-8h"),
    ("Cephalexin", "21-28 days", "25 mg/kg/dose q6h (max 125 mg/dose)", "25-100 mg/kg/day q6-8h"),
    ("Cefazolin", "<29 weeks (0-14 days)", "25 mg/kg/dose q12h", "50-100 mg/kg/day, max 6 g/day q6-8h"),
    ("Cefazolin", "30-36 weeks (0-14 days) / >45 weeks (any age)", "25 mg/kg/dose q12h", "50-100 mg/kg/day, max 6 g/day q6-8h"),
    ("Cefazolin", "37-45 weeks (0-7 days) / >7 days", "25 mg/kg/dose q12h or q8h", "50-100 mg/kg/day, max 6 g/day q6-8h"),
    ("Ceftazidime", "<29 weeks (0-28 days) / ≥28 days", "30 mg/kg/dose q12h-q8h", "100-150 mg/kg/day; cystic fibrosis/meningitis 150-200 mg/kg/day q6-8h"),
    ("Ceftazidime", "30-36 weeks (0-7 days) / >7 days", "30 mg/kg/dose q8h", "100-150 mg/kg/day; cystic fibrosis/meningitis 150-200 mg/kg/day q6-8h"),
    ("Ceftazidime", "37-45 weeks (0-7 days) / >7 days / >45 weeks", "30 mg/kg/dose q8h", "100-150 mg/kg/day; cystic fibrosis/meningitis 150-200 mg/kg/day q6-8h"),
    ("Cefotaxime", "<29 weeks (0-7 days)", "50 mg/kg/dose q12h", "100-200 mg/kg/day; meningitis 300 mg/kg/day q6-8h"),
    ("Cefotaxime", "<32 weeks / >32 weeks", "50 mg/kg/dose q8h-q6h", "100-200 mg/kg/day; meningitis 300 mg/kg/day q6-8h"),
    ("Ceftriaxone", "Sepsis", "50 mg/kg/dose q24h", "50-100 mg/kg/day"),
    ("Ceftriaxone", "Meningitis", "100 mg/kg/dose loading, then 50 mg/kg/dose q24h", "Meningitis 100 mg/kg/dose q12-24h"),
    ("Ampicillin", "<29 weeks (0-28 days) / ≥28 days", "50 mg/kg/dose q12h-q8h", "200 mg/kg/dose; meningitis 300 mg/kg/dose q6h"),
    ("Ampicillin", "30-36 weeks (0-14 days) / >14 days", "50 mg/kg/dose q12h-q8h", "200 mg/kg/dose; meningitis 300 mg/kg/dose q6h"),
    ("Ampicillin", "37-44 weeks (0-7 days) / >7 days / >45 weeks", "50 mg/kg/dose q8h-q6h", "200 mg/kg/dose; meningitis 300 mg/kg/dose q6h"),
    ("Penicillin G", "<29 weeks to >45 weeks (bacteremia)", "25,000-50,000 units/kg/dose q12h", "Bacteremia 100,000-300,000 units/kg/day, max 12-20 MU/day q4-6h"),
    ("Penicillin G", "Meningitis (all ages)", "75,000-1,00,000 units/kg/dose q8h", "Meningitis 75,000-1,00,000 units/kg/dose q4-6h"),
    ("Piperacillin/tazobactam", "<29 weeks (0-28 days) / ≥28 days", "50 mg/kg/dose q12h", "100 mg/kg/dose q8h"),
    ("Piperacillin/tazobactam", "30-36 weeks (0-14 days) / >14 days / 37-44 weeks (0-7 days) / >7 days", "50-100 mg/kg/dose q12h-q8h", "100 mg/kg/dose q8h"),
    ("Ciprofloxacin", "Premature (32-37 weeks) / term neonates / >37 weeks", "10-15 mg/kg/dose q12h", "PO 20-40 mg/kg/day divided; IV 20-30 mg/kg/day, max 1.2 g/day q12h"),
    ("Clindamycin", "<29 weeks (0-28 days) / ≥28 days", "5-7.5 mg/kg/dose q12h-q8h", "PO 20-40 mg/kg/day, max 1.8 g/day; IV 20-30 mg/kg/day, max 1.2 g/day"),
    ("Clindamycin", "30-36 weeks (0-14 days) / >14 days / 37-44 weeks (0-7 days) / >7 days / >45 weeks", "5-7.5 mg/kg/dose q8h", "PO 20-40 mg/kg/day, max 1.8 g/day; IV 20-30 mg/kg/day, max 1.2 g/day"),
    ("Clarithromycin", "Neonates", "7.5 mg/kg/dose q12h", "PO/IV 7.5 mg/kg/dose, max 1 g/day"),
    ("Erythromycin", "Pneumonitis/conjunctivitis", "12.5 mg/kg/dose q6h for 14 days", "Base/ethylsuccinate/stearate: 40-50 mg/kg/day divided q6-8h, max daily dose 4 g/day; some labeling divides daily dose q12h"),
    ("Metoclopramide (prokinetic)", "PMA-based", "10 mg/kg/dose q6h for 2 days, then 4 mg/kg/dose q6h for 5 days", "3 mg/kg/dose 4 times daily; may increase to 10 mg/kg/dose; max dose 250 mg/dose"),
    ("Colistin", "PMA-based", "Loading 5 mg/kg, then 2.5-5 mg/kg/dose q12h", "2.5-5 mg/kg/day bid"),
    ("Linezolid (PO and IV)", "Neonates <7 days / >7 days", "10 mg/kg/dose q8h", ">12 years 15 mg/kg/dose (or per adult dosing), max 1.2 g/day; ≤12 years max 1.2 g/day tid"),
    ("Metronidazole", "<29 weeks (0-28 days)", "7.5 mg/kg/dose q48h", "IV/PO 30-40 mg/kg/day q6-8h"),
    ("Metronidazole", "≥28 days / 30-36 weeks (0-14 days)", "7.5 mg/kg/dose q24h", "IV/PO 30-40 mg/kg/day q6-8h"),
    ("Metronidazole", ">14 days / 37-44 weeks (0-7 days)", "7.5 mg/kg/dose q12h", "IV/PO 30-40 mg/kg/day q6-8h"),
    ("Metronidazole", ">7 days / >45 weeks", "7.5 mg/kg/dose q8hrly", "IV/PO 30-40 mg/kg/day q6-8h"),
    ("Rifampin (PO)", "32-38 weeks (0-28 days)", "5 mg/kg/dose q12h", "Oral 15-20 mg/kg/day once daily, max 600 mg/dose"),
    ("Rifampin (PO)", ">38 weeks (0-7 days) / 8-28 days", "5-10 mg/kg/dose q12h", "2 months-12 years: PO/IV 6-12 mg/kg q12hrly. For PCP (PO/IV): 15-20 mg/kg/day q6-8h"),
    ("Trimethoprim/sulfamethoxazole", "-", "3 mg/kg TMP base as a single dose, then 2-3 mg/kg/day q12h", "2 months-12 years: PO/IV 6-12 mg/kg/day q12hrly; for PCP (PO/IV) 15-20 mg/kg/day q6-8h"),
    ("Vancomycin", "29 weeks (0-14 days) / >14 days / 30-36 weeks (0-14 days) / >14 days / >45 weeks", "10-15 mg/kg/dose q12-8hrly", "IV: initial 45-60 mg/kg/day divided q6-8h"),
    ("Fosfomycin", "PMA <40 weeks", "100 mg/kg/day in 2 divided doses", "Premature infants 100 mg/kg/day; 1-12 years 200-800 mg/kg/day (max 8 g/dose, loading dose may increase to 8 g), Q12h max 24 g/day; PO 100-200 mg/kg/day, max 1.5 g/dose Q8h"),
    ("Nitrofurantoin", "N/A", "N/A", "PO 5-7 mg/kg/day q6h"),
]
PEDS_NEONATAL_COLUMNS = ["Drug", "PMA / Age", "Neonatal Dose", "Pediatric Dose"]
PEDS_NEONATAL_NOTES = (
    "PMA = post-menstrual age. Rows are split by the age/weight brackets given in the source table — read "
    "each row as a self-contained bracket. Source references cited in the original document: Pediatric "
    "Formulary Committee (BNF for Children 2019-2020), The Harriet Lane Handbook (21st ed.), UpToDate, "
    "NeoFax (IBM, 2020)."
)


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
    st.session_state.filter_aware = []
    st.session_state.view_mode = "🔍 Drug Lookup"
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

    cat = aware_category(data)
    if cat:
        aware_badge = badge(f"WHO AWaRe: {cat}", AWARE_TONE[cat])
    else:
        aware_badge = badge("WHO AWaRe: not classified", "grey")

    st.markdown(activity + renal + pregnancy + allergy + aware_badge, unsafe_allow_html=True)


def build_summary_text(key, data):
    lines = [f"{data['generic']} ({data['brand']})", "=" * 40, f"Source: {data.get('source', 'N/A')}", ""]
    for field, label in FIELD_LABELS:
        lines.append(f"{label}: {data.get(field, 'N/A')}")
    lines.append("")
    lines.append("Generated by the Antimicrobial Stewardship App.")
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


def render_empiric_regimens():
    st.subheader("🏥 Empiric Regimens by Clinical Scenario")
    st.info(
        f"**Source: {GUIDELINE_SOURCE}**, Chapter 1 — Empiric Antibiotic Regimens. "
        "This is one hospital's local protocol, built around its own antibiogram and formulary. "
        "It is transcribed here for reference and was not independently re-verified line-by-line "
        "against the source PDF beyond careful reading — cross-check the cited page number in the "
        "original document before relying on any specific dose, and always defer to your own "
        "institution's protocol and local antibiogram where they differ."
    )

    with st.expander("🔒 Restricted & Controlled Antibiotics (institutional formulary policy)"):
        st.markdown(
            "**Restricted** — pre-authorization from an ID physician is mandatory. In critically "
            "ill patients or off-hours, a 24-hour dose can be given, but approval is still required "
            "afterward or the drug will not be dispensed further:"
        )
        st.write(", ".join(RESTRICTED_ANTIBIOTICS))
        st.markdown(
            "**Controlled** — therapy can start without pre-authorization, but cultures must be "
            "sent before initiating and the regimen adjusted once results are back; if cultures "
            "show no growth and therapy continues beyond 72 hours, an ID consult should be obtained:"
        )
        st.write(", ".join(CONTROLLED_ANTIBIOTICS))
        st.caption(
            "This is that institution's own formulary policy — separate from, and not the same list "
            "as, the WHO AWaRe classification used elsewhere in this app."
        )

    search = st.text_input(
        "🔎 Search scenarios by indication (e.g., \"cellulitis\", \"meningitis\", \"UTI\") — "
        "leave blank to browse by category instead",
        key="scenario_search",
    )

    categories = list(EMPIRIC_REGIMEN_SCENARIOS.keys())
    category = st.selectbox("Category", categories, key="scenario_category")

    if search:
        needle = search.strip().lower()
        matches = [
            (cat, s) for cat, block in EMPIRIC_REGIMEN_SCENARIOS.items()
            for s in block["scenarios"] if needle in s["indication"].lower()
        ]
        if not matches:
            st.warning(f"No scenario indication matches '{search}'. Try a shorter or different term, or clear the box to browse by category below.")
        for cat, s in matches:
            st.markdown(f"**{s['indication']}** — *{cat}* (p. {EMPIRIC_REGIMEN_SCENARIOS[cat]['pages']})")
            render_scenario_card(s)
        return

    block = EMPIRIC_REGIMEN_SCENARIOS[category]
    st.caption(f"Source pages: {block['pages']}")
    if block.get("notes"):
        st.caption(f"ℹ️ {block['notes']}")

    for s in block["scenarios"]:
        st.markdown(f"#### {s['indication']}")
        render_scenario_card(s)
        st.divider()


def render_scenario_card(s):
    if s.get("first_line"):
        st.success(f"**First line:** {s['first_line']}")
    if s.get("alternative"):
        st.info(f"**Alternative:** {s['alternative']}")
    if s.get("notes"):
        st.caption(f"ℹ️ {s['notes']}")


def render_misc_infections():
    st.subheader("🦠 Miscellaneous Infections — Viral, Fungal, Parasitic")
    st.info(
        f"**Source: {GUIDELINE_SOURCE}**, Chapter 4 — Treatment for Miscellaneous Infections. "
        "This is one hospital's local protocol, transcribed here for reference and not independently "
        "re-verified line-by-line against the source PDF beyond careful reading — cross-check the cited "
        "page number in the original document before relying on any specific dose, and always defer to "
        "your own institution's protocol where it differs. The malaria regimen in particular is "
        "summarized only; see the note on that entry."
    )

    search = st.text_input(
        "🔎 Search by indication (e.g., \"candidiasis\", \"scabies\", \"herpes\") — "
        "leave blank to browse by category instead",
        key="misc_search",
    )

    categories = list(MISC_INFECTIONS.keys())
    category = st.selectbox("Category", categories, key="misc_category")

    if search:
        needle = search.strip().lower()
        matches = [
            (cat, s) for cat, block in MISC_INFECTIONS.items()
            for s in block["scenarios"] if needle in s["indication"].lower()
        ]
        if not matches:
            st.warning(f"No indication matches '{search}'. Try a shorter or different term, or clear the box to browse by category below.")
        for cat, s in matches:
            st.markdown(f"**{s['indication']}** — *{cat}* (p. {MISC_INFECTIONS[cat]['pages']})")
            render_scenario_card(s)
        return

    block = MISC_INFECTIONS[category]
    st.caption(f"Source pages: {block['pages']}")
    if block.get("notes"):
        st.caption(f"ℹ️ {block['notes']}")

    for s in block["scenarios"]:
        st.markdown(f"#### {s['indication']}")
        render_scenario_card(s)
        st.divider()


def render_special_populations():
    st.subheader("💊 Safety & Dosing in Special Populations")
    st.info(
        f"**Source: {GUIDELINE_SOURCE}**, Chapter 6 — Safety and Dosing in Special Populations. "
        "Reference tables for pregnancy/lactation, dialysis/CRRT, hepatic adjustment, CSF penetration, "
        "monitoring, and normal dosing. Treat this as a first-draft transcription — verify any specific "
        "number against the source PDF page cited in each tab before using it in patient care, and always "
        "defer to your own institution's protocol where it differs."
    )

    tabs = st.tabs([
        "🤰 Pregnancy & Lactation", "💉 Vaccines in Pregnancy", "🩸 Dialysis & CRRT Dosing",
        "🫀 Hepatic Adjustment & CSF", "🧪 Long-Term Monitoring", "👤 Adult Normal Doses",
        "👶 Pediatric & Neonatal Doses",
    ])

    with tabs[0]:
        st.caption("Source page: 76-78")
        st.dataframe(
            pd.DataFrame(PREG_LACT_ROWS, columns=PREG_LACT_COLUMNS),
            width="stretch", hide_index=True,
        )
        st.caption(f"ℹ️ {PREG_LACT_NOTES}")

    with tabs[1]:
        st.caption("Source page: 79-80")
        st.dataframe(
            pd.DataFrame(VACCINE_PREG_ROWS, columns=VACCINE_PREG_COLUMNS),
            width="stretch", hide_index=True,
        )
        st.caption(f"ℹ️ {VACCINE_PREG_NOTES}")

    with tabs[2]:
        st.caption("Source page: 81-85")
        st.dataframe(
            pd.DataFrame(DIALYSIS_ROWS, columns=DIALYSIS_COLUMNS),
            width="stretch", hide_index=True,
        )
        st.caption(f"ℹ️ {DIALYSIS_NOTES}")

    with tabs[3]:
        st.caption("Source page: 86")
        st.markdown("**Hepatic dose adjustment required for:**")
        hc1, hc2, hc3 = st.columns(3)
        hc1.markdown("*Antibacterial*\n\n" + "\n".join(f"- {d}" for d in HEPATIC_ADJUSTMENT["Antibacterial"]))
        hc2.markdown("*Antifungal*\n\n" + "\n".join(f"- {d}" for d in HEPATIC_ADJUSTMENT["Antifungal"]))
        hc3.markdown("*Antiviral*\n\n" + "\n".join(f"- {d}" for d in HEPATIC_ADJUSTMENT["Antiviral"]))
        st.divider()
        st.markdown("**Penetration of antimicrobials into CSF**")
        for label, drugs in CSF_PENETRATION.items():
            st.markdown(f"*{label}*")
            st.write(", ".join(drugs))
        st.caption(f"ℹ️ {CSF_NOTES}")

    with tabs[4]:
        st.caption("Source page: 87-88")
        st.dataframe(
            pd.DataFrame(LONGTERM_LABS_ROWS, columns=LONGTERM_LABS_COLUMNS),
            width="stretch", hide_index=True,
        )
        st.caption(f"ℹ️ {LONGTERM_LABS_NOTES}")

    with tabs[5]:
        st.caption("Source page: 89-93")
        st.dataframe(
            pd.DataFrame(ADULT_DOSES_ROWS, columns=ADULT_DOSES_COLUMNS),
            width="stretch", hide_index=True,
        )
        st.caption(f"ℹ️ {ADULT_DOSES_NOTES}")

    with tabs[6]:
        st.caption("Source page: 94-97")
        st.dataframe(
            pd.DataFrame(PEDS_NEONATAL_ROWS, columns=PEDS_NEONATAL_COLUMNS),
            width="stretch", hide_index=True,
        )
        st.caption(f"ℹ️ {PEDS_NEONATAL_NOTES}")


def render_stewardship_guidance():
    st.subheader("📚 Antimicrobial Stewardship — Guidance Summary")
    st.caption(
        "A condensed summary of the frameworks referenced throughout this app, drawn from WHO, "
        "CDC, and AHRQ publications. This is an educational summary, not a reproduction of the "
        "source documents — read the linked originals for full detail before building policy on them."
    )

    tab_aware, tab_core, tab_moments = st.tabs([
        "🎯 WHO AWaRe", "🏥 CDC Core Elements", "⏱️ 4 Moments Framework",
    ])

    with tab_aware:
        st.markdown(
            "The WHO **AWaRe** classification sorts antibiotics into three groups to guide "
            "empiric choice and monitor overuse of broad-spectrum/last-resort agents:"
        )
        st.markdown(
            badge("Access", "green") +
            " First-choice, narrow-spectrum agents with lower resistance potential — the agents "
            "that should cover most common infections empirically.",
            unsafe_allow_html=True,
        )
        st.markdown(
            badge("Watch", "yellow") +
            " Broader-spectrum agents with higher resistance potential — appropriate for more "
            "severe presentations or specific indications, but shouldn't be reflexive first-line choices.",
            unsafe_allow_html=True,
        )
        st.markdown(
            badge("Reserve", "red") +
            " Last-resort agents for confirmed or strongly suspected multidrug-resistant "
            "organisms — WHO recommends these be guided by infectious disease/stewardship input "
            "and tracked closely at the facility level.",
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown("**This app's curated database, by AWaRe category:**")
        counts = {cat: 0 for cat in ALL_AWARE}
        not_classified = []
        for k, d in ANTIMICROBIALS.items():
            cat = aware_category(d)
            if cat:
                counts[cat] += 1
            else:
                not_classified.append(d["generic"])
        cols = st.columns(len(ALL_AWARE) + 1)
        for col, cat in zip(cols, ALL_AWARE):
            col.metric(cat, counts[cat])
        cols[-1].metric("Not classified", len(not_classified))
        if not_classified:
            st.caption(f"Not part of WHO's general AWaRe list: {', '.join(not_classified)}.")
        st.caption(
            "A stewardship goal used by many programs (echoing WHO's 2023 target) is that the "
            "large majority of empiric antibiotic use — commonly cited around 70% — should fall "
            "in the Access category. Use the sidebar's AWaRe filter to browse each group."
        )

    with tab_core:
        st.markdown(
            "CDC's **Core Elements** framework (hospital and outpatient versions) gives "
            "stewardship programs a common structure. Both settings now share the same seven elements:"
        )
        core_elements = [
            ("1. Leadership Commitment", "Dedicate the human, financial, and IT resources needed, with visible senior leadership support."),
            ("2. Accountability", "Name a leader (or co-leaders, e.g. a physician and pharmacist) responsible for program outcomes."),
            ("3. Pharmacy Expertise / Setting-specific Expertise", "Pair stewardship expertise with clinical expertise relevant to the care setting."),
            ("4. Action", "Implement concrete interventions — prospective audit and feedback, preauthorization, clinical decision support, treatment guidelines."),
            ("5. Tracking", "Monitor prescribing patterns, intervention impact, and outcomes like C. difficile rates and resistance trends."),
            ("6. Reporting", "Regularly share prescribing and outcome data with prescribers, pharmacy, nursing, and leadership."),
            ("7. Education", "Train prescribers, pharmacy staff, nurses, and patients — most effective paired with active interventions, not alone."),
        ]
        for title, desc in core_elements:
            st.markdown(f"**{title}**")
            st.write(desc)
        st.caption(
            "Source: CDC Core Elements of Hospital Antibiotic Stewardship Programs and Core "
            "Elements of Outpatient Antibiotic Stewardship (links below)."
        )

    with tab_moments:
        st.markdown(
            "AHRQ's **Four Moments of Antibiotic Decision Making** is a bedside framework for "
            "prescribers to talk through at each stage of a patient's antibiotic course:"
        )
        moments = [
            ("Moment 1", "Does this patient have an infection that requires antibiotics?"),
            ("Moment 2", "Have I ordered appropriate cultures before starting antibiotics? What empiric therapy should I initiate?"),
            ("Moment 3", "A day or more has passed. Can I stop antibiotics? Can I narrow therapy? Can I change from IV to oral therapy?"),
            ("Moment 4", "What duration of antibiotic therapy is needed for my patient's diagnosis?"),
        ]
        for title, desc in moments:
            st.info(f"**{title}** — {desc}")
        st.caption("Source: AHRQ Safety Program for Improving Antibiotic Use (link below).")

    st.divider()
    st.markdown("**Sources**")
    st.markdown(
        "- [WHO AWaRe antibiotic classification](https://aware.essentialmeds.org/)\n"
        "- [CDC — Core Elements of Hospital Antibiotic Stewardship Programs](https://www.cdc.gov/antibiotic-use/hcp/core-elements/hospital.html)\n"
        "- [CDC — Core Elements of Outpatient Antibiotic Stewardship](https://www.cdc.gov/antibiotic-use/media/pdfs/Core-Elements-Outpatient-508.pdf)\n"
        "- [AHRQ — Four Moments of Antibiotic Decision Making](https://www.ahrq.gov/antibiotic-use/acute-care/four-moments/index.html)"
    )


# ---------------------------------------------------------------------------
# SIDEBAR — controls (rendered before the main content depends on them)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.radio(
        "View",
        [
            "🔍 Drug Lookup", "🆚 Compare Two Drugs", "🏥 Empiric Regimens",
            "🦠 Other Infections", "💊 Special Populations & Dosing",
            "📚 Stewardship Guidance",
        ],
        key="view_mode",
    )
    st.checkbox("⚠️ Patient has PCN anaphylaxis history", key="pcn_allergy")

    st.divider()
    st.subheader("🔎 Filter the drug list")
    filter_classes = st.multiselect("Drug class", ALL_CLASSES, key="filter_classes")
    filter_coverage = st.multiselect("Organism coverage", ALL_COVERAGE, key="filter_coverage")
    filter_aware = st.multiselect(
        "WHO AWaRe category", ALL_AWARE, key="filter_aware",
        help="Access = first-choice, narrow-spectrum. Watch = higher resistance potential, use judiciously. Reserve = last-resort, ID/stewardship-guided.",
    )

    st.divider()
    with st.expander(f"📇 Browse all {len(ANTIMICROBIALS)} drugs by class", expanded=False):
        st.caption("A second way to find a drug — click any name below to jump straight to it, alongside the search dropdown in the main panel.")
        _classes_grouped = {}
        for _k in sorted(ANTIMICROBIALS, key=label_for):
            _classes_grouped.setdefault(ANTIMICROBIALS[_k]["drug_class"], []).append(_k)
        for _cls in sorted(_classes_grouped):
            st.markdown(f"**{_cls}**")
            for _k in _classes_grouped[_cls]:
                st.button(label_for(_k), key=f"navclass_{_k}", on_click=jump_to_drug, args=(label_for(_k),), width="stretch")

# ---------------------------------------------------------------------------
# FILTERED OPTION LIST
# ---------------------------------------------------------------------------
def matches_filters(key):
    d = ANTIMICROBIALS[key]
    if filter_classes and d["drug_class"] not in filter_classes:
        return False
    if filter_coverage and not any(tag in d["coverage"] for tag in filter_coverage):
        return False
    if filter_aware and d.get("aware") not in filter_aware:
        return False
    return True


filtered_keys = sorted([k for k in ANTIMICROBIALS if matches_filters(k)], key=label_for)

# ---------------------------------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------------------------------
st.title("🧫 Antimicrobial Stewardship App")
st.warning(
    "⚠️ **Clinical decision-support reference only.** Verify all dosing and clinical decisions "
    "against institutional protocols, your local antibiogram, and current full prescribing "
    "information before use in patient care."
)
st.caption("Search by generic or brand name. Use the sidebar to filter by drug class, organism coverage, or WHO AWaRe category, flag a PCN allergy, compare two agents, or read the stewardship guidance summary.")

if st.session_state.view_mode == "📚 Stewardship Guidance":
    render_stewardship_guidance()
elif st.session_state.view_mode == "🏥 Empiric Regimens":
    render_empiric_regimens()
elif st.session_state.view_mode == "🦠 Other Infections":
    render_misc_infections()
elif st.session_state.view_mode == "💊 Special Populations & Dosing":
    render_special_populations()
elif not filtered_keys:
    st.info("No curated drugs match the current filters — clear a filter in the sidebar.")
else:
    if st.session_state.view_mode == "🆚 Compare Two Drugs":
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
    f"Antimicrobial Stewardship App — curated content for teaching/reference purposes. "
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
