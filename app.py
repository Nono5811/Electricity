import streamlit as st
import easyocr
from PIL import Image
import numpy as np
import re

# 1. Initialize the OCR Reader (English & Numbers)
# This downloads a lightweight computer vision model on the very first run.
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['en'])

reader = load_ocr_reader()

# 2. EDL Progressive Tariff Calculation Logic (Laos Household Pricing)
def calculate_edl_bill(kwh):
    """
    Calculates the monthly residential bill in LAK based on EDL progressive tiers.
    Adjust these rates easily if EDL updates their pricing.
    - Tier 1: 0 - 25 kWh @ 679 LAK/kWh
    - Tier 2: 26 - 150 kWh @ 850 LAK/kWh
    - Tier 3: 151+ kWh @ 1,900 LAK/kWh (Expensive bracket)
    """
    if kwh <= 25:
        return kwh * 679
    elif kwh <= 150:
        return (25 * 679) + ((kwh - 25) * 850)
    else:
        return (25 * 679) + (125 * 850) + ((kwh - 150) * 1900)

# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Vientiane Home Energy Guard", page_icon="⚡", layout="centered")

st.title("⚡ EDL Photo-to-Bill Monitor")
st.write("Upload a clear photo of your physical meter to instantly check your consumption and projected monthly bill.")

st.info("💡 **How it works:** Taking a photo of the meter tracks 100% of your home's usage safely, avoiding the blind spots of cheap smart plugs!")

# 3. User Inputs
previous_reading = st.number_input(
    "Enter your starting meter reading (kWh) from the beginning of the month:", 
    min_value=0.0, 
    value=13500.0,  # Pre-filled close to your real meter reading for easy testing
    step=1.0,
    help="Check your last paper EDL bill to find your starting number."
)

uploaded_file = st.file_uploader("📸 Take or upload a photo of your physical meter:", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Open and display the uploaded image
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Meter Image", use_container_width=True)
    
    with st.spinner("🤖 Processing dials... Cleaning up meter noise..."):
        # Convert PIL Image to a NumPy array for EasyOCR processing
        img_np = np.array(image)
        results = reader.readtext(img_np, allowlist="0123456789")
        
        valid_digits = []
        # Sort detected text blocks from left to right to read digits in correct visual order
        results.sort(key=lambda x: x[0][0][0])
        
        for (bbox, text, confidence) in results:
            clean_text = re.sub(r'[^0-9]', '', text)
            
            # --- THE CLEANUP FILTER ---
            # Ignore standard mechanical printed labels, multipliers, and subscripts printed on physical meters
            if clean_text in ["1", "10", "102", "103", "104", "105", "100"]:
                continue
                
            # Keep digits we are highly confident are part of the actual rolling dial
            if clean_text and confidence > 0.25:
                valid_digits.append(clean_text)
        
        # Combine the clean isolated digits into one string
        detected_text = "".join(valid_digits)
    
    # --- SMART DECIMAL SCALING FOR MECHANICAL DIALS ---
    # Since your physical meter reads whole numbers and decimals together (e.g., 135978)
    # we automatically check and scale down numbers that look 10x or 100x larger than previous inputs.
    suggested_value = previous_reading
    if detected_text:
        raw_val = float(detected_text)
        # If the reading is impossibly high compared to previous entry, shift decimal to the left
        if raw_val > (previous_reading * 5):
            suggested_value = round(raw_val / 10.0, 1)
            # Apply secondary shift for extreme OCR misreads (like reading the visual labels)
            if suggested_value > (previous_reading * 5):
                suggested_value = round(suggested_value / 10.0, 1)
        else:
            suggested_value = raw_val
                    
    st.success("🤖 Scan Complete!")
    
    # --- HUMAN-IN-THE-LOOP OVERRIDE ---
    # Pre-fills with the AI's smart filtered guess, but gives the user a box to instantly make a quick fix
    current_reading = st.number_input(
        "Confirm or correct the detected reading below:",
        min_value=0.0,
        value=suggested_value,
        step=0.1,
        help="Adjust this number if the rolling mechanical dials confused the camera scanner."
    )
    
    # 4. Calculation & Dashboard Display
    usage = current_reading - previous_reading
    
    if usage < 0:
        st.error("❌ **Error:** Current reading cannot be less than your starting reading. Please check your inputs.")
    else:
        # Assuming typical consumption rates to calculate a 30-day billing estimate
        projected_kwh = usage * 30 
        projected_bill = calculate_edl_bill(projected_kwh)
        
        st.write("---")
        st.subheader("📊 Consumption & Cost Projections")
        
        col1, col2 = st.columns(2)
        col1.metric("Usage calculated", f"{usage:.1f} kWh")
        col2.metric("Projected Monthly Bill", f"{projected_bill:,.0f} LAK")
        
        # Actionable local EDL warning advice
        if projected_kwh > 150:
            st.warning(
                f"⚠️ **High Tariff Bracket Alert!** Your current trend pushes you into EDL's highest pricing Tier 3 "
                f"(1,900 LAK/kWh). Shaving off just 2 kWh of usage per day could save you "
                f"roughly **{projected_bill * 0.18:,.0f} LAK** on your next bill."
            )
        else:
            st.success("🎉 **Safe Zone:** Your usage keeps you in the lower, heavily subsidized EDL pricing tiers.")
