import streamlit as st
import easyocr
from PIL import Image, ImageOps
import numpy as np
import re
import cv2 # We now need to import cv2 for more advanced preprocessing

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

# --- SPATIAL FILTERING ENGINE ---
def process_ocr_results(results, image_width):
    y_centers = []
    valid_candidates = []
    
    for (bbox, text, confidence) in results:
        clean_text = re.sub(r'[^0-9]', '', text)
        if clean_text and confidence > 0.15:
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
        y_tolerance = 100 # Custom tolerance for better filtering on these specific meters
        
        for item in valid_candidates:
            if abs(item["y_center"] - median_y) < y_tolerance:
                final_digits.append(item["text"])
    
    return "".join(final_digits)


# --- IMAGE PREPROCESSING ---
def preprocess_image(image):
    # Convert PIL Image to OpenCV image (BGR format)
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    # 1. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Apply Gaussian Blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # 3. Apply Adaptive Thresholding (this is the crucial step for binarization)
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 11, 2)
    
    return thresh

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
    # 1. Open the image
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Meter Image", use_container_width=True)
    
    with st.spinner("🤖 Processing dials... Cleaning up image noise..."):
        # 2. Advanced Preprocessing with OpenCV
        processed_img_np = preprocess_image(image)
        
        # Display the processed image to the user so they can see what the OCR is analyzing
        st.write("🔧 Processed image for OCR:")
        st.image(processed_img_np, caption="Binarized Image (Black & White)", use_container_width=True, channels="GRAY")
        
        # 3. Read text from processed image
        results = reader.readtext(processed_img_np, allowlist="0123456789")
        
        # 4. Use the custom spatial filtering engine
        detected_text = process_ocr_results(results, processed_img_np.shape[1])

    # --- READING EVALUATION ---
    current_reading = None
    
    if detected_text:
        try:
            # Handle potential scientific notation if OCR gets very confused
            if 'e' in detected_text.lower():
                # We can't handle scientific notation from meter reading OCR,
                # it's highly likely to be wrong.
                raise ValueError("Scientific notation detected")

            current_reading = float(detected_text)
            st.success(f"🤖 Scan Complete! Detected Current Reading: **{current_reading:,.1f} kWh**")
            
            # Show the raw detected string for transparency
            st.info(f"📁 Raw digits pulled directly from image: `{detected_text}`")
            
        except ValueError:
            st.error("❌ **Error:** Could not parse the numbers found in the image. The detected text seems incorrect. Please use a clearer photo.")
    else:
        st.error("❌ **Error:** No numbers detected on the meter baseline. Make sure the numbers are centered and well-lit.")

    # --- CALCULATIONS & METRICS ---
    if current_reading is not None:
        usage = current_reading - previous_reading
        
        if usage < 0:
            st.error(
                f"❌ **Reading Mismatch:** The scanned reading ({current_reading:,.1f} kWh) is lower than your "
                f"starting reading ({previous_reading:,.1f} kWh). "
                f"If the image only showed the last few digits, you may need to adjust your photo angle."
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
