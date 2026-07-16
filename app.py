import streamlit as st
import easyocr
from PIL import Image
import numpy as np
import re

# 1. Initialize the OCR Reader
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['en'])

reader = load_ocr_reader()

# 2. EDL Progressive Tariff Calculation Logic
def calculate_edl_bill(kwh):
    if kwh <= 25:
        return kwh * 679
    elif kwh <= 150:
        return (25 * 679) + ((kwh - 25) * 850)
    else:
        return (25 * 679) + (125 * 850) + ((kwh - 150) * 1900)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Vientiane Home Energy Guard", page_icon="⚡", layout="centered")

st.title("⚡ EDL Photo-to-Bill Monitor")
st.write("Upload a clear photo of your physical meter to instantly check your consumption and projected monthly bill.")

# User Inputs (Starting point for the month)
previous_reading = st.number_input(
    "Enter your starting meter reading (kWh) from the beginning of the month:", 
    min_value=0.0, 
    value=135000.0,
    step=1.0
)

uploaded_file = st.file_uploader("📸 Take or upload a photo of your physical meter:", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Meter Image", use_container_width=True)
    
    with st.spinner("🤖 Processing dials... Filtering background noise..."):
        img_np = np.array(image)
        results = reader.readtext(img_np, allowlist="0123456789")
        
        # --- SPATIAL FILTERING ENGINE ---
        y_centers = []
        valid_candidates = []
        
        for (bbox, text, confidence) in results:
            clean_text = re.sub(r'[^0-9]', '', text)
            if clean_text and confidence > 0.2:
                y_coords = [point[1] for point in bbox]
                y_center = sum(y_coords) / 4.0
                y_centers.append(y_center)
                valid_candidates.append({
                    "text": clean_text,
                    "y_center": y_center,
                    "x_start": bbox[0][0],
                    "confidence": confidence
                })
        
        final_digits = []
        if y_centers:
            valid_candidates.sort(key=lambda x: x["x_start"])
            median_y = np.median(y_centers)
            y_tolerance = img_np.shape[0] * 0.15 # Allow 15% vertical drift
            
            for item in valid_candidates:
                if abs(item["y_center"] - median_y) < y_tolerance:
                    if item["text"] in ["1", "10", "102", "103", "104", "105"]:
                        continue
                    final_digits.append(item["text"])
        
        detected_text = "".join(final_digits)

    # --- AUTOMATED READING RECONSTRUCTION ---
    current_reading = previous_reading
    
    if detected_text:
        try:
            raw_val = float(detected_text)
            
            # Reconstruction logic for missing leading digits (e.g., shadows on the first number)
            if raw_val < previous_reading and len(str(int(raw_val))) < len(str(int(previous_reading))):
                diff_len = len(str(int(previous_reading))) - len(str(int(raw_val)))
                prefix = str(int(previous_reading))[:diff_len]
                corrected_text = prefix + str(int(raw_val))
                current_reading = float(corrected_text)
            else:
                current_reading = raw_val
                
            st.success(f"🤖 Scan Complete! Detected Current Reading: **{current_reading:,.1f} kWh**")
            
        except ValueError:
            st.error("❌ **Error:** Could not process the digits found in the image. Please use a clearer photo.")
            current_reading = None
    else:
        st.error("❌ **Error:** No numbers detected on the meter baseline. Please check the lighting and alignment.")
        current_reading = None

    # --- CALCULATIONS & METRICS ---
    if current_reading is not None:
        usage = current_reading - previous_reading
        
        if usage < 0:
            st.error(
                f"❌ **Reading Mismatch:** The scanned reading ({current_reading:,.1f} kWh) is lower than your "
                f"starting reading ({previous_reading:,.1f} kWh). The photo might be blurry or cut off."
            )
        else:
            projected_kwh = usage * 30 
            projected_bill = calculate_edl_bill(projected_kwh)
            
            st.write("---")
            st.subheader("📊 Consumption & Cost Projections")
            
            col1, col2 = st.columns(2)
            col1.metric("Calculated Usage", f"{usage:.1f} kWh")
            col2.metric("Projected Monthly Bill", f"{projected_bill:,.0f} LAK")
            
            if projected_kwh > 150:
                st.warning(
                    f"⚠️ **High Tariff Bracket Alert!** Your current trend pushes you into EDL's highest pricing Tier 3. "
                    f"Reducing daily usage by just 2 kWh could save you roughly **{projected_bill * 0.18:,.0f} LAK** this month."
                )
            else:
                st.success("🎉 **Safe Zone:** Your usage keeps you in the lower, heavily subsidized EDL pricing tiers.")
