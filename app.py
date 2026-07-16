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

# User Inputs
previous_reading = st.number_input(
    "Enter your starting meter reading (kWh) from the beginning of the month:", 
    min_value=0.0, 
    value=135000.0,  # Adjusted closer to your actual range
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
        # 1. Find the vertical centers (Y-coordinates) of all detected text blocks
        y_centers = []
        valid_candidates = []
        
        for (bbox, text, confidence) in results:
            clean_text = re.sub(r'[^0-9]', '', text)
            if clean_text and confidence > 0.2:
                # Calculate the vertical center of this bounding box
                y_coords = [point[1] for point in bbox]
                y_center = sum(y_coords) / 4.0
                y_centers.append(y_center)
                valid_candidates.append({
                    "text": clean_text,
                    "y_center": y_center,
                    "x_start": bbox[0][0],
                    "confidence": confidence
                })
        
        # 2. Identify the main horizontal row (the row with the most numbers)
        # We group things that share a similar Y-level
        final_digits = []
        if y_centers:
            # Sort candidates from left to right based on X-coordinate
            valid_candidates.sort(key=lambda x: x["x_start"])
            
            # Find the median Y coordinate of the longest digit blocks
            # The main meter dials are the most prominent numbers, so their Y level is our baseline
            median_y = np.median(y_centers)
            
            # Keep only the numbers that sit close to this main horizontal baseline
            # This instantly drops the labels underneath because they are lower down (larger Y values)
            y_tolerance = img_np.shape[0] * 0.15 # Allow 15% vertical drift
            
            for item in valid_candidates:
                if abs(item["y_center"] - median_y) < y_tolerance:
                    # Ignore the common small labels if they somehow slip through
                    if item["text"] in ["1", "10", "102", "103", "104", "105"]:
                        continue
                    final_digits.append(item["text"])
        
        detected_text = "".join(final_digits)
    
    # --- INTELLIGENT READING RECONSTRUCTION ---
    # Since the first digit '1' was in shadow and dropped, we check if the reading
    # is suddenly way lower than the previous reading. If it is, we automatically
    # restore the correct leading digit.
    suggested_value = previous_reading
    if detected_text:
        raw_val = float(detected_text)
        
        # If the detected number is missing the leading digit (e.g. 35978 instead of 135978)
        if raw_val < previous_reading and len(str(int(raw_val))) < len(str(int(previous_reading))):
            # Grab the prefix from the previous reading (e.g. "1") and prepend it
            diff_len = len(str(int(previous_reading))) - len(str(int(raw_val)))
            prefix = str(int(previous_reading))[:diff_len]
            corrected_text = prefix + str(int(raw_val))
            suggested_value = float(corrected_text)
        else:
            suggested_value = raw_val
                    
    st.success("🤖 Scan Complete!")
    
    # Human Override Box
    current_reading = st.number_input(
        "Confirm or correct the detected reading below:",
        min_value=0.0,
        value=suggested_value,
        step=1.0,
    )
    
    usage = current_reading - previous_reading
    
    if usage < 0:
        st.error("❌ **Error:** Current reading cannot be less than your starting reading.")
    else:
        projected_kwh = usage * 30 
        projected_bill = calculate_edl_bill(projected_kwh)
        
        st.write("---")
        st.subheader("📊 Consumption & Cost Projections")
        
        col1, col2 = st.columns(2)
        col1.metric("Usage calculated", f"{usage:.1f} kWh")
        col2.metric("Projected Monthly Bill", f"{projected_bill:,.0f} LAK")
        
        if projected_kwh > 150:
            st.warning(
                f"⚠️ **High Tariff Bracket Alert!** Your current trend pushes you into EDL's highest pricing Tier 3. "
                f"Reducing daily usage by just 2 kWh could save you roughly **{projected_bill * 0.18:,.0f} LAK** this month."
            )
        else:
            st.success("🎉 **Safe Zone:** Your usage keeps you in the lower, heavily subsidized EDL pricing tiers.")
