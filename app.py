import streamlit as st
import easyocr
from PIL import Image
import numpy as np
import re
import cv2

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

# --- IMAGE PREPROCESSING ENGINE ---
# --- IMAGE PREPROCESSING ENGINE ---
def preprocess_image(image):
    # Convert PIL Image to OpenCV BGR format
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Reduce noise while keeping dial edges sharp
    filtered = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Apply Otsu's thresholding
    _, thresh = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Force inversion to make the dial box white and numbers black
    thresh = cv2.bitwise_not(thresh)
    
    # --- AUTOMATIC METER BOX CROPPING & BORDER CLEANING ---
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_box = None
    max_area = 0
    img_h, img_w = thresh.shape
    
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        aspect_ratio = w / float(h)
        
        if aspect_ratio > 3.0 and aspect_ratio < 7.0 and w > (img_w * 0.4):
            if area > max_area:
                max_area = area
                best_box = (x, y, w, h)
                
    if best_box:
        x, y, w, h = best_box
        
        # Shave off 6% from borders to aggressively eliminate line remnants
        pad_x = int(w * 0.06)
        pad_y = int(h * 0.06)
        crop = thresh[y+pad_y : y+h-pad_y, x+pad_x : x+w-pad_x]
        
        # --- NOISE CLEANING ENGINE (Remove stray specks under/around numbers) ---
        # Invert temporarily to find black components on white background
        binary_inv = cv2.bitwise_not(crop)
        n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_inv, connectivity=8)
        
        # Create a clean white canvas
        cleaned_inv = np.zeros_like(binary_inv)
        
        # Keep only solid components that look like actual digits (ignoring tiny dots)
        min_digit_pixel_size = 40 
        for i in range(1, n_labels):
            if stats[i, cv2.CC_STAT_AREA] >= min_digit_pixel_size:
                cleaned_inv[labels == i] = 255
                
        # Re-invert back to original format (Black text on White background)
        crop = cv2.bitwise_not(cleaned_inv)
        
        # Add a clean, generous white border back around the shaved image
        padded = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        return padded
        
    return thresh
# --- STREAMLIT UI ---
st.set_page_config(page_title="Vientiane Home Energy Guard", page_icon="⚡", layout="centered")

st.title("⚡ EDL Photo-to-Bill Monitor")
st.write("Upload a clear photo of your physical meter to instantly check your consumption and projected monthly bill.")

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
    
    with st.spinner("🤖 Processing dials... Cleaning up image noise..."):
        processed_img_np = preprocess_image(image)
        
        st.write("🔧 Processed image for OCR:")
        st.image(processed_img_np, caption="Solid Character Binarization", use_container_width=True, channels="GRAY")
        
        # Scan text
        results = reader.readtext(processed_img_np, allowlist="0123456789")
        
        # --- SPATIAL & CONTENT FILTERING ENGINE ---
        y_centers = []
        valid_candidates = []
        
        for (bbox, text, confidence) in results:
            clean_text = re.sub(r'[^0-9]', '', text)
            
            # CRUCIAL FILTER: Ignore the standard meter multiplier text row underneath the dials
            if clean_text in ["1", "10", "102", "103", "104", "105", "106"]:
                continue
                
            if clean_text and confidence > 0.20:
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
            # Group text pieces moving from left to right
            valid_candidates.sort(key=lambda x: x["x_start"])
            
            # Find the baseline row where the actual dial digits rest
            median_y = np.median(y_centers)
            y_tolerance = processed_img_np.shape[0] * 0.12 # Tightened to ignore rows above/below dials
            
            for item in valid_candidates:
                if abs(item["y_center"] - median_y) < y_tolerance:
                    final_digits.append(item["text"])
        
        detected_text = "".join(final_digits)

    # --- READING EVALUATION ---
    current_reading = None
    
    if detected_text:
        try:
            current_reading = float(detected_text)
            st.success(f"🤖 Scan Complete! Detected Current Reading: **{current_reading:,.1f} kWh**")
            st.info(f"📁 Raw digits pulled directly from image: `{detected_text}`")
            
        except ValueError:
            st.error("❌ **Error:** Could not parse the numbers found in the image.")
    else:
        st.error("❌ **Error:** No meter digits detected. Please check the alignment.")

    # --- CALCULATIONS & METRICS ---
    if current_reading is not None:
        usage = current_reading - previous_reading
        
        if usage < 0:
            st.error(
                f"❌ **Reading Mismatch:** The scanned reading ({current_reading:,.1f} kWh) is lower than your "
                f"starting reading ({previous_reading:,.1f} kWh)."
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
                st.warning(f"⚠️ **High Tariff Bracket Alert!** Trend puts you into EDL Tier 3.")
            else:
                st.success("🎉 **Safe Zone:** Lower subsidized EDL pricing tiers.")

final_digits = []
        if y_centers:
            valid_candidates.sort(key=lambda x: x["x_start"])
            median_y = np.median(y_centers)
            y_tolerance = processed_img_np.shape[0] * 0.12 
            
            for item in valid_candidates:
                if abs(item["y_center"] - median_y) < y_tolerance:
                    final_digits.append(item["text"])
        
        # Combine everything and force pull exactly the first 6 digits to drop trailing dial ticks
        raw_combined = "".join(final_digits)
        detected_text = raw_combined[:6]
