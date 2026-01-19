import streamlit as st
import time
import json
import zipfile
import io
import concurrent.futures
from openai import OpenAI

# --- Configuration ---
st.set_page_config(page_title="BizOnboard Builder", page_icon="🚀", layout="centered")

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #f0f2f6; }
    .stTextInput>div>div>input, .stSelectbox>div>div>div { 
        background-color: #1e293b; color: white; border-radius: 10px; border: 1px solid #334155; 
        padding: 10px; font-size: 16px;
    }
    div.stButton > button { 
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); 
        color: white; border: none; padding: 12px 24px; border-radius: 8px; 
        font-weight: 600; width: 100%; margin-top: 20px;
    }
    .question-text { font-size: 24px; font-weight: 600; margin-bottom: 10px; color: #e2e8f0; }
    .sub-text { font-size: 16px; color: #94a3b8; margin-bottom: 20px; }
    
    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- STATE MANAGEMENT ---
if "q_step" not in st.session_state: st.session_state.q_step = 1
if "data" not in st.session_state: st.session_state.data = {}

# --- ATTRIBUTE MAPPINGS ---
ATTRIBUTE_DEFAULTS = {
    "eCommerce Product": ["Size", "Color", "Material", "Fit", "Brand"],
    "Hotel / Accommodation": ["Room Type", "Bed Type", "View", "Amenities", "Meal Plan"],
    "Travel Package": ["Duration", "Destination", "Inclusions", "Hotel Category"],
    "Rental Product": ["Duration Unit", "Deposit", "Condition", "Usage Limits"],
    "Service": ["Duration", "Location", "Level", "Provider Type"]
}

# --- HELPER FUNCTIONS ---
def next_step():
    st.session_state.q_step += 1

def create_zip(pages_dict):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_title, html_content in pages_dict.items():
            filename = "index.html"
            zip_file.writestr(filename, html_content)
    return zip_buffer.getvalue()

# --- API KEY MANAGEMENT (UPDATED) ---
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except FileNotFoundError:
    st.error("Secrets file not found. Please add your OpenAI API Key to `.streamlit/secrets.toml`.")
    st.stop()
except KeyError:
    st.error("OpenAI API Key not found in secrets. Please check your configuration.")
    st.stop()

def generate_dalle_image(image_prompt):
    client = OpenAI(api_key=api_key)
    try:
        response = client.images.generate(
            model="dall-e-3", prompt=image_prompt, size="1024x1024", quality="standard", n=1
        )
        return response.data[0].url
    except Exception:
        return "https://placehold.co/1024x1024/222/FFF?text=Image+Generation+Error"

def generate_final_package(model_name, data):
    client = OpenAI(api_key=api_key)
    attributes_final = ", ".join(data.get('final_attributes', []))
    
    prompt = f"""
    You are a Business Onboarding & Product Setup Assistant.
    
    User Data:
    - Business: {data.get('name')} ({data.get('type')})
    - Industry: {data.get('industry')}
    - Model: {data.get('business_model')}
    - Category: {data.get('main_cat')} > {data.get('sub_cat')}
    - Product: {data.get('prod_name')} ({data.get('prod_desc')})
    - Brand: {data.get('brand')}
    - Segment: {data.get('segment')}
    - Attributes: {attributes_final}
    - Website: {data.get('website_url', 'None')}
    
    TASK 1: Generate a detailed JSON structure populated with 3 realistic sample products based on the inputs.
    - Define 'variants' and 'pricing_rules' logic appropriate for the {data.get('business_model')}.
    
    TASK 2: Generate a SINGLE HTML Home Page (index.html).
    - It must act as a Landing Page + Catalog.
    - Display the "Sample Products" in a grid.
    - Use :root CSS variables based on the vibe '{data.get('vibe')}'.
    
    OUTPUT JSON STRUCTURE (Strict):
    {{
        "business_details": {{ "name": "{data.get('name')}", "model": "{data.get('business_model')}", "segment": "{data.get('segment')}" }},
        "category_structure": {{ "main": "{data.get('main_cat')}", "sub": "{data.get('sub_cat')}" }},
        "attribute_set": {{ "name": "Custom Set", "attributes": {json.dumps(data.get('final_attributes', []))} }},
        "sample_products": [
            {{
                "id": "P001",
                "name": "{data.get('prod_name')}",
                "description": "{data.get('prod_desc')}",
                "brand": "{data.get('brand')}",
                "price": 100,
                "attributes": {{ "Attribute_Name": "Value" }},
                "variants": [ {{ "sku": "V1", "spec": "Option 1", "stock": 10 }} ],
                "pricing_rules": [ {{ "name": "Rule", "rule": "Description" }} ]
            }}
        ],
        "marketing_banner_html": "<div>...</div>",
        "ui_pages": {{
            "Home": "Full HTML5 string (index.html). Hero image: 'HERO_IMAGE_PLACEHOLDER'."
        }}
    }}
    """
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": "You are a JSON factory."}, {"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        return json.loads(content)
    except Exception as e:
        return {"error": str(e)}

# --- UI: SIDEBAR ---
with st.sidebar:
    st.title("💎 Config")
    # API Key Input Removed - Using Secrets
    
    if st.button("Restart"):
        st.session_state.clear()
        st.rerun()

# --- MAIN QUESTIONNAIRE LOGIC ---
step = st.session_state.q_step

# Container for centering
with st.container():
    
    # 1. Business Name
    if step == 1:
        st.markdown('<div class="question-text">1. What is your Business Name?</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q1")
        if st.button("Next ➝"):
            if val: 
                st.session_state.data["name"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 2. Business Type
    elif step == 2:
        st.markdown('<div class="question-text">2. What is your Business Type?</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-text">Examples: Agency, SaaS, Store, Consultancy, Brand</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q2")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["type"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 3. Industry
    elif step == 3:
        st.markdown('<div class="question-text">3. Which Industry are you in?</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-text">Examples: Fashion, Real Estate, Travel, Education</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q3")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["industry"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 4. Location
    elif step == 4:
        st.markdown('<div class="question-text">4. Is your business Virtual/Online or a Physical Shop?</div>', unsafe_allow_html=True)
        val = st.radio("Select Option:", ["Virtual/Online", "Physical Shop"], label_visibility="collapsed")
        if st.button("Next ➝"):
            st.session_state.data["location"] = val
            next_step()
            st.rerun()

    # 5. Website Check
    elif step == 5:
        st.markdown('<div class="question-text">5. Do you already have a website?</div>', unsafe_allow_html=True)
        val = st.radio("Select Option:", ["Yes", "No"], label_visibility="collapsed")
        if st.button("Next ➝"):
            st.session_state.data["has_website"] = val
            # Logic: If Yes, go to Step 6 (URL). If No, skip to Step 7 (eCommerce).
            if val == "Yes":
                st.session_state.q_step = 6
            else:
                st.session_state.q_step = 7
            st.rerun()

    # 6. Website URL (Conditional)
    elif step == 6:
        st.markdown('<div class="question-text">5b. What is your Website URL?</div>', unsafe_allow_html=True)
        val = st.text_input("URL", key="q6")
        if st.button("Next ➝"):
            st.session_state.data["website_url"] = val
            st.session_state.q_step = 7
            st.rerun()

    # 7. eCommerce Check
    elif step == 7:
        st.markdown('<div class="question-text">6. Is this an eCommerce business?</div>', unsafe_allow_html=True)
        val = st.radio("Select Option:", ["Yes", "No"], label_visibility="collapsed")
        if st.button("Next ➝"):
            st.session_state.data["is_ecommerce"] = val
            next_step()
            st.rerun()

    # 8. Theme/Vibe
    elif step == 8:
        st.markdown('<div class="question-text">7. Describe your Theme & Vibe</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-text">Examples: Minimalist, Luxury, Bold, Corporate</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q8")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["vibe"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 9. Focus Areas
    elif step == 9:
        st.markdown('<div class="question-text">8. Select your focus areas</div>', unsafe_allow_html=True)
        val = st.multiselect("Select Options:", ["Website", "eCommerce", "Marketing", "Growth", "Analytics"])
        if st.button("Confirm & Move to Product Setup ➝"):
            if val:
                st.session_state.data["focus"] = val
                next_step()
                st.rerun()
            else: st.error("Select at least one")

    # --- PHASE 2: PRODUCT SETUP ---

    # 10. Business Model
    elif step == 10:
        st.markdown('<div class="question-text">Select ONE Business Model</div>', unsafe_allow_html=True)
        val = st.radio("Model:", [
            "eCommerce Product", "Hotel / Accommodation", "Travel Package", 
            "Rental Product", "Service"
        ], label_visibility="collapsed")
        
        if st.button("Next ➝"):
            st.session_state.data["business_model"] = val
            next_step()
            st.rerun()

    # 11. Main Category
    elif step == 11:
        st.markdown('<div class="question-text">What is your Main Category?</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-text">Examples: Clothing, Hotel Rooms, Tour Packages</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q11")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["main_cat"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 12. Sub Category
    elif step == 12:
        st.markdown('<div class="question-text">Do you want to add a Sub-Category?</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-text">Example: Men -> T-Shirts</div>', unsafe_allow_html=True)
        val = st.text_input("Answer (or type 'None')", key="q12")
        if st.button("Next ➝"):
            st.session_state.data["sub_cat"] = val if val else "General"
            next_step()
            st.rerun()

    # 13. Attributes
    elif step == 13:
        model = st.session_state.data["business_model"]
        defaults = ATTRIBUTE_DEFAULTS.get(model, [])
        
        st.markdown(f'<div class="question-text">Attribute Setup for {model}</div>', unsafe_allow_html=True)
        st.info(f"We suggest these attributes: **{', '.join(defaults)}**")
        
        st.markdown('<div class="sub-text">Do you want to use this attribute set or customize it?</div>', unsafe_allow_html=True)
        mode = st.radio("Mode:", ["Use Suggested", "Customize"], label_visibility="collapsed")
        
        if st.button("Next ➝"):
            st.session_state.data["attr_mode"] = mode
            if mode == "Use Suggested":
                st.session_state.data["final_attributes"] = defaults
                st.session_state.q_step = 15 # Skip custom step
            else:
                st.session_state.q_step = 14 # Go to custom step
            st.rerun()

    # 14. Customize Attributes (Conditional)
    elif step == 14:
        model = st.session_state.data["business_model"]
        defaults = ATTRIBUTE_DEFAULTS.get(model, [])
        
        st.markdown('<div class="question-text">Customize your Attributes</div>', unsafe_allow_html=True)
        
        # Allow removing or adding
        final_attrs = st.multiselect("Select/Remove Attributes:", defaults + ["Weight", "Gender", "Warranty", "Expiry", "Material"], default=defaults)
        new_attr = st.text_input("Add a new attribute manually:")
        
        if st.button("Confirm Attributes ➝"):
            if new_attr and new_attr not in final_attrs:
                final_attrs.append(new_attr)
            st.session_state.data["final_attributes"] = final_attrs
            next_step()
            st.rerun()

    # 15. Product Name
    elif step == 15:
        st.markdown('<div class="question-text">1. Product / Service Name</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q15")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["prod_name"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 16. Short Description
    elif step == 16:
        st.markdown('<div class="question-text">2. Short Description</div>', unsafe_allow_html=True)
        val = st.text_area("Answer", key="q16")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["prod_desc"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 17. Brand/Provider
    elif step == 17:
        st.markdown('<div class="question-text">3. Brand or Provider Name</div>', unsafe_allow_html=True)
        val = st.text_input("Answer", key="q17")
        if st.button("Next ➝"):
            if val:
                st.session_state.data["brand"] = val
                next_step()
                st.rerun()
            else: st.error("Required")

    # 18. Target Segment
    elif step == 18:
        st.markdown('<div class="question-text">4. Target Segment</div>', unsafe_allow_html=True)
        val = st.selectbox("Select One:", ["B2C (Consumer)", "B2B (Business)", "Luxury", "Budget", "Premium"])
        if st.button("Finish & Generate 🚀"):
            st.session_state.data["segment"] = val
            next_step()
            st.rerun()

    # --- GENERATION STEP ---
    elif step == 19:
        data = st.session_state.data
        
        if "result" not in st.session_state:
            st.info("⚡ Generating Single Home Page & Product Data...")
            img_prompt = f"Professional hero image for {data.get('name')}, {data.get('business_model')}. Theme: {data.get('vibe')}."
            
            with st.spinner("Processing..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    f_gpt = executor.submit(generate_final_package, "gpt-4o", data)
                    f_img = executor.submit(generate_dalle_image, img_prompt)
                    res = f_gpt.result()
                    img_url = f_img.result()
                
                if "ui_pages" in res and "Home" in res["ui_pages"]:
                    res["ui_pages"]["Home"] = res["ui_pages"]["Home"].replace("HERO_IMAGE_PLACEHOLDER", img_url)
                
                st.session_state.result = res
                st.session_state.img_url = img_url

        if "result" in st.session_state:
            res = st.session_state.result
            
            st.success("✅ Generation Complete!")
            
            tab1, tab2, tab3 = st.tabs(["🖥️ Home Page", "📦 Product Data", "📥 Download"])
            
            with tab1:
                st.components.v1.html(res.get("ui_pages", {}).get("Home", ""), height=800, scrolling=True)
            
            with tab2:
                st.subheader("Structured Data")
                st.json(res.get("sample_products"))
                st.write("**Attributes:**")
                st.json(res.get("attribute_set"))
            
            with tab3:
                if "Home" in res.get("ui_pages", {}):
                    zip_data = create_zip(res["ui_pages"])
                    st.download_button("Download Home Page (.zip)", zip_data, "home.zip", "application/zip")
                st.download_button("Download Data (.json)", json.dumps(res, indent=2), "data.json", "application/json")
                
            if st.button("Start New Project"):
                st.session_state.clear()
                st.rerun()
