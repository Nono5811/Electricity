import streamlit as st
import easyocr
from PIL import Image
import numpy as np
import re

# 1. Initialize the OCR Reader (English/Numbers)
# This will download a lightweight AI model on the first run.
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['en'])

reader = load_ocr_reader()

# 2. EDL Progressive Tariff Calculation Logic
def calculate_edl_bill(kwh):
    """
    Calculates the bill in LAK based on total kWh consumed.
    Uses progressive pricing tiers:
    - Tier 1: 0 - 25 kWh @ 679 LAK
    - Tier 2: 26 - 150 kWh @ 850 LAK
    - Tier 3: 151+ kWh @ 1,900 LAK
    """
    if kwh <= 25:
        return kwh * 679
    elif kwh <= 150:
        return (25 * 679) + ((kwh - 25) * 850)
    else:
        return (25 * 679) + (125 * 850) + ((kwh - 150) * 1900)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Vientiane Energy Saver", page_icon="⚡")
st.title("⚡ EDL Photo-to-Bill Monitor")
st.write("Upload a clear photo of your home's electricity meter to instantly track your bill trends.")

# Input the previous reading so we can calculate the usage difference
previous_reading = st.number_input(
    "Enter your starting meter reading (kWh) from the beginning of the month:", 
    min_value=0.0, 
    value=12300.0,
    step=1.0
)

uploaded_file = st.file_uploader("Take/Upload a photo of your physical meter", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Display the uploaded image
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Meter Image", use_container_width=True)
    
    with st.spinner("Parsing numbers from image..."):
        # Convert PIL Image to a NumPy array for EasyOCR
        img_np = np.array(image)
        
        # Read the text from the image
        # Using allowlist forces the AI to only look for digits
        results = reader.readtext(img_np, allowlist="0123456789.")
        
        # Extract the largest numeric string found (usually the main meter dial)
        detected_numbers = []
        for (bbox, text, confidence) in results:
            # Clean up the parsed text (keep only numbers and dots)
            clean_text = re.sub(r'[^0-9.]', '', text)
            if clean_text and confidence > 0.4:  # Only trust read confidence above 40%
                detected_numbers.append((float(clean_text), confidence))
                
    if detected_numbers:
        # Grab the detected reading with the highest confidence
        detected_numbers.sort(key=lambda x: x[1], reverse=True)
        current_reading = detected_numbers[0][0]
        
        st.success(f"🤖 AI Detected Meter Reading: **{current_reading:,.1f} kWh**")
        
        # Calculate consumption
        usage = current_reading - previous_reading
        
        if usage < 0:
            st.error("Error: Detected reading is lower than your starting monthly reading. Please check the image.")
        else:
            # Project monthly use based on average daily rates
            projected_kwh = usage * 30  # Assumes this is a 1-day step, adjust as needed for testing
            projected_bill = calculate_edl_bill(projected_kwh)
            
            # --- DISPLAY DASHBOARD ---
            st.write("---")
            st.subheader("📊 Consumption & Cost Projections")
            
            col1, col2 = st.columns(2)
            col1.metric("Usage Since Last Read", f"{usage:.1f} kWh")
            col2.metric("Projected Monthly Bill", f"{projected_bill:,.0f} LAK")
            
            # Warning threshold for the expensive EDL Tier 3 (over 150 kWh)
            if projected_kwh > 150:
                st.warning(
                    f"⚠️ **High Tariff Bracket Alert!** your current trend pushes you into Tier 3 "
                    f"({1900} LAK/kWh). Reducing daily usage by just 2 kWh could save you "
                    f"roughly {projected_bill * 0.18:,.0f} LAK this month."
                )
            else:
                st.success("🎉 Safe Zone: Your usage keeps you in the lower, subsidized EDL price tiers.")
    else:
        st.error("Could not confidently read digits from the image. Please try taking a closer, clearer photo in better lighting.")
