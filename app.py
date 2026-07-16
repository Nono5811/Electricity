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
    
    with st.spinner("Analyzing meter dials..."):
        # Convert PIL Image to a NumPy array for EasyOCR
        img_np = np.array(image)
        results = reader.readtext(img_np, allowlist="0123456789")
        
        # --- THE FIX: Filter out known EDL meter subscript noise ---
        valid_digits = []
        
        # Sort detected blocks from left to right so we read the dials in order
        results.sort(key=lambda x: x[0][0][0])
        
        for (bbox, text, confidence) in results:
            clean_text = re.sub(r'[^0-9]', '', text)
            
            # IGNORE common physical meter labels that mess up the reading
            if clean_text in ["1", "10", "102", "103", "104", "105", "100"]:
                continue
                
            if clean_text and confidence > 0.25:
                valid_digits.append(clean_text)
        
        # Combine the remaining real dial numbers
        detected_text = "".join(valid_digits)
                    
    st.info("🤖 **AI Scan Complete.**")
    
    # Pre-fill the input box with our smart-filtered guess
    current_reading = st.number_input(
        "Confirm or correct the detected reading below:",
        min_value=0.0,
        value=float(detected_text) if detected_text else previous_reading,
        step=1.0
    )
    
    # Calculate consumption
    usage = current_reading - previous_reading
    
    if usage < 0:
        st.error("Error: Current reading cannot be less than your starting reading.")
    else:
        projected_kwh = usage * 30 
        projected_bill = calculate_edl_bill(projected_kwh)
        
        st.write("---")
        st.subheader("📊 Cost Projections")
        col1, col2 = st.columns(2)
        col1.metric("Usage calculated", f"{usage:.1f} kWh")
        col2.metric("Projected Monthly Bill", f"{projected_bill:,.0f} LAK")
