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
        
        # --- THE FIX: Filter by the physically largest text block ---
        best_text = ""
        max_height = 0
        
        for (bbox, text, confidence) in results:
            clean_text = re.sub(r'[^0-9]', '', text)
            if clean_text and confidence > 0.3:
                # Calculate the height of this specific text block
                y_coords = [point[1] for point in bbox]
                height = max(y_coords) - min(y_coords)
                
                # We want the text block with the tallest height (the big dials)
                if height > max_height:
                    max_height = height
                    best_text = clean_text
                    
    st.info("🤖 **AI Scan Complete.**")
    
    # Pre-fill the input with our smart-filtered guess
    current_reading = st.number_input(
        "Confirm or correct the detected reading below:",
        min_value=0.0,
        value=float(best_text) if best_text else previous_reading,
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
        
