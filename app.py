import streamlit as st
import time
import json
import zipfile
import io
import concurrent.futures
from openai import OpenAI

# --- Configuration ---
st.set_page_config(page_title="BizOnboard Builder", page_icon="🚀", layout="wide")

# --- Custom CSS (Fixed for Overlapping & JSON) ---
st.markdown("""
<style>
    /* Main App Background */
    .stApp { background-color: #0e1117; color: #f0f2f6; }
    
    /* Padding to prevent scroll cutoff */
    .block-container { padding-bottom: 5rem; }

    /* Input Fields */
    .stTextInput>div>div>input, .stSelectbox>div>div>div { 
        background-color: #1e293b; color: white; border-radius: 10px; border: 1px solid #334155; padding: 10px; font-size: 16px;
    }
    
    /* Chat Bubbles */
    .stChatMessage { background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; margin-bottom: 15px; }
    
    /* Buttons */
    div.stButton > button { 
        background: linear-gradient(135deg, #00C853 0%, #009688 100%); color: white; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; margin-top: 10px;
    }
    
    /* JSON Styling - Fixed Overlap & added Scroll */
    div[data-testid="stJson"] {
        background-color: #151922; 
        padding: 20px; 
        border-radius: 10px; 
        border: 1px solid #334155;
        white-space: pre-wrap; 
        word-wrap: break-word;
        overflow-y: auto;
        max-height: 500px;
    }

    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #1e293b; border-radius: 5px; padding: 5px 15px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #00C853; }

    .element-container { margin-bottom: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# --- SECRETS MANAGEMENT ---
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except FileNotFoundError:
    st.error("⚠️ Secrets file not found. Please create `.streamlit/secrets.toml` and add your `OPENAI_API_KEY`.")
    st.stop()
except KeyError:
    st.error("⚠️ `OPENAI_API_KEY` not found in secrets. Please configure it in your Streamlit dashboard.")
    st.stop()

# --- STATE MANAGEMENT ---
if "step" not in st.session_state: st.session_state.step = 0
if "data" not in st.session_state: st.session_state.data = {}
if "generation_complete" not in st.session_state: st.session_state.generation_complete = False
if "show_success" not in st.session_state: st.session_state.show_success = False
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your BizOnboard Builder.\n\nLet's build a complete **Data-Driven Digital Presence**. First, what is your **Business Name**?"}]

# --- CONSTANTS ---
BUSINESS_TYPES = [
    "Service-Based Business", "Professional Service Business", "E-commerce Store",
    "Product-Based Business", "Asset / Transaction-Based Business", "Digital Product / Service Business"
]

INDUSTRY_OPTIONS = [
    "Architecture & Design", "Hospitality & Tourism", "Real Estate & Property Development",
    "Healthcare & Medical Services", "Retail & Consumer Goods"
]

STRUCTURE_OPTIONS = ["Single Page", "Multi Page", "Landing Page"]

SEGMENT_OPTIONS = [
    "B2C (Individual Consumers)", "B2B (Businesses / Companies)",
    "B2B2C (Businesses serving end customers)", "D2C (Direct to Consumer)", "Niche / Enthusiast Audience"
]

INDUSTRY_TO_MODELS = {
    "Architecture & Design": ["Architectural Service", "Interior Design", "Landscape Design", "Consultation Service"],
    "Hospitality & Tourism": ["Hotel / Accommodation", "Travel Package", "Restaurant / Cafe", "Event / Venue"],
    "Real Estate & Property Development": ["Property Sales", "Rental Property", "Property Management", "Development Project"],
    "Healthcare & Medical Services": ["Medical Service", "Clinic / Hospital", "Telehealth", "Wellness / Therapy"],
    "Retail & Consumer Goods": ["E-commerce Product", "Retail Store", "Wholesale / B2B", "Subscription Box"]
}

ATTRIBUTE_DEFAULTS = {
    "E-commerce Product": { "Fashion/Apparel": ["Size", "Color", "Material", "Fit"], "Electronics": ["Brand", "Model", "Specs"], "General": ["Weight", "Dimensions"] },
    "Retail Store": ["Category", "Availability", "Location", "Price"],
    "Hotel / Accommodation": ["Room Type", "Bed Config", "View", "Amenities", "Meal Plan"],
    "Travel Package": ["Duration", "Destination", "Inclusions", "Hotel Category"],
    "Restaurant / Cafe": ["Cuisine", "Dietary Info", "Spiciness", "Portion"],
    "Medical Service": ["Service Type", "Doctor", "Fee", "Duration"],
    "Telehealth": ["Platform", "Duration", "Specialist"],
    "Property Sales": ["Type", "Area", "Bedrooms", "Price", "Location"],
    "Rental Property": ["Type", "Rent", "Deposit", "Available From"],
    "Architectural Service": ["Project Type", "Style", "Sq Ft", "Timeline"],
    "Interior Design": ["Room Type", "Style", "Budget", "Materials"],
    "General Service": ["Duration", "Level", "Provider", "Location"]
}

CUSTOM_ATTR_POOLS = {
    "Hotel / Accommodation": ["Pet Friendly", "Parking", "Pool Access", "Smoking Policy", "Floor Level", "Accessibility", "Cancellation Policy"],
    "Travel Package": ["Group Size", "Guide Language", "Visa Requirements", "Start City", "End City", "Age Limit"],
    "Restaurant / Cafe": ["Allergens", "Calorie Count", "Chef Special", "Serving Temp", "Pairing"],
    "Property Sales": ["Parking Spaces", "Year Built", "Facing Direction", "Floor Number", "Gated Community"],
    "Rental Property": ["Lease Term", "Security Deposit", "Maintenance Fee", "Furnishing Details", "Pet Policy"],
    "Medical Service": ["Insurance Accepted", "Languages Spoken", "Experience", "Gender of Doctor", "Wheelchair Access"],
    "Telehealth": ["Platform Used", "Recording Available", "Prescription Digital"],
    "E-commerce Product": ["Weight", "Warranty Period", "Return Policy", "Country of Origin", "Fragile", "Eco-friendly", "Expiry Date"],
    "Retail Store": ["Store Hours", "Parking", "Fitting Rooms", "Payment Methods"],
    "Architectural Service": ["Green Certification", "3D Rendering", "Permit Handling", "Revisions Included"],
    "Interior Design": ["Color Palette", "Furniture Sourcing", "Lighting Plan", "Vastu/Feng Shui"],
    "General Service": ["Urgency Fee", "Revisions", "Source Files", "Support Period"]
}

# --- HELPER FUNCTIONS ---
def get_suggestion_pool(model_key, industry):
    if model_key in CUSTOM_ATTR_POOLS: return CUSTOM_ATTR_POOLS[model_key]
    if industry == "Hospitality & Tourism": return CUSTOM_ATTR_POOLS["Hotel / Accommodation"]
    elif industry == "Real Estate & Property Development": return CUSTOM_ATTR_POOLS["Property Sales"]
    elif industry == "Healthcare & Medical Services": return CUSTOM_ATTR_POOLS["Medical Service"]
    elif industry == "Retail & Consumer Goods": return CUSTOM_ATTR_POOLS["E-commerce Product"]
    return CUSTOM_ATTR_POOLS["General Service"]

def create_zip(pages_dict):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_title, html_content in pages_dict.items():
            filename = "index.html" if page_title.lower() == "home" else f"{page_title.lower().replace(' ', '_')}.html"
            zip_file.writestr(filename, html_content)
    return zip_buffer.getvalue()

def generate_dalle_image(api_key, image_prompt):
    client = OpenAI(api_key=api_key)
    try:
        response = client.images.generate(model="dall-e-3", prompt=image_prompt, size="1024x1024", quality="standard", n=1)
        return response.data[0].url
    except Exception:
        return "https://placehold.co/1024x1024/222/FFF?text=Image+Generation+Error"

def generate_business_package(api_key, model_name, data):
    client = OpenAI(api_key=api_key)
    model_type = data.get('business_model', 'General')
    structure = data.get('structure', 'Single Page')
    attributes_final = ", ".join(data.get('final_attributes', []))
    
    if structure == "Single Page":
        structure_rules = "Generate a Single-Page website. All content vertically stacked on index.html with anchor links. Sticky Header."
        json_hint = '"ui_pages": { "Home": "Full HTML5 string..." }'
    elif structure == "Multi Page":
        structure_rules = "Generate a Multi-Page website. Separate HTML strings for Home, About, Services, Contact. Navbar links to files."
        json_hint = '"ui_pages": { "Home": "<html>...", "About": "<html>...", "Services": "<html>...", "Contact": "<html>..." }'
    else: 
        structure_rules = "Generate a Landing Page. Focus on conversion, Hero, Benefits, CTA. Single file."
        json_hint = '"ui_pages": { "Home": "Full HTML5 string..." }'

    prompt = f"""
    You are a Lead UI/UX Architect.
    Client: {data.get('name')} | Industry: {data.get('industry')} | Model: {model_type}
    Structure: {structure} | Product: {data.get('prod_name')} | Attributes: {attributes_final}
    
    **DESIGN MANDATE:**
    1. **COLOR PALETTE:** Auto-generate a premium palette based on '{data.get('industry')}'. Use CSS :root variables.
    2. **LOGO:** CSS-styled Logo Brand Mark in Navbar (FontAwesome Icon + Google Font).
    3. **UI:** Modern CSS (Flexbox, Grid, Shadows, Hover Effects).
    
    TASK 1: Generate Data (JSON). Auto-generate suitable Product Descriptions.
    TASK 2: Generate Website Structure.
    *** STRICT RULES FOR '{structure}' ***
    {structure_rules}
    
    OUTPUT JSON (Strict):
    {{
        "business_details": {{ "name": "String", "model": "{model_type}", "structure": "{structure}" }},
        "categories_tree": [ {{ "id": 1, "name": "Auto-Main", "children": [ {{ "id": 2, "name": "Auto-Sub" }} ] }} ],
        "attribute_sets": [ {{ "name": "Custom Set", "attributes": {json.dumps(data.get('final_attributes', []))} }} ],
        "sample_products": [
            {{
                "id": "P001", "name": "{data.get('prod_name')}", "description": "Auto-generated...", "price": 100,
                "attributes": {{ "Attr": "Val" }}, "variants": [ {{ "sku": "V1", "spec": "Var1", "stock": 10 }} ],
                "pricing_rules": [ {{ "name": "Rule", "rule": "Desc" }} ]
            }}
        ],
        "marketing_banner_html": "<div style='padding: 15px; text-align: center; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; font-weight: bold;'>🚀 Launch Offer!</div>",
        {json_hint}
    }}
    Constraints: Return ONLY raw JSON. No markdown.
    """
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": "You are a JSON factory."}, {"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        return json.loads(content), prompt
    except Exception as e:
        return {"error": str(e)}, prompt

# --- CHAT LOGIC ---
def add_msg(role, content):
    st.session_state.messages.append({"role": role, "content": content})

def process_input(text):
    step = st.session_state.step
    data = st.session_state.data
    text = text.strip()

    if step == 0:
        data["name"] = text
        add_msg("assistant", f"Welcome **{text}**! Select your **Business Type** below:")
        st.session_state.step = 1
    elif step == 4.1:
        data["website_url"] = text
        add_msg("assistant", f"URL Saved. Is this an **eCommerce business**?")
        st.session_state.step = 5
    elif step == 13:
        data["prod_name"] = text
        st.session_state.step = 15

# --- UI: SIDEBAR ---
with st.sidebar:
    st.title("💎 Design Config")
    if st.button("Restart", type="primary"):
        st.session_state.clear()
        st.rerun()
    # Model Selection (Hidden, hardcoded to gpt-5)
    selected_model = "gpt-5"

# --- UI: CHAT ---
if st.session_state.step <= 15:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    text_steps = [0, 4.1, 13]
    if st.session_state.step in text_steps:
        if prompt := st.chat_input("Type answer..."):
            with st.chat_message("user"):
                st.markdown(prompt)
            add_msg("user", prompt)
            time.sleep(0.2)
            process_input(prompt)
            st.rerun()

    # --- STEP HANDLERS ---
    elif st.session_state.step == 1:
        with st.chat_message("assistant"):
            st.write("**Select Business Type:**")
            b_type = st.radio("Choose One:", BUSINESS_TYPES, index=None, key="type_radio")
            if b_type:
                if st.button("Confirm Type"):
                    st.session_state.data["business_type"] = b_type
                    add_msg("assistant", f"Selected: **{b_type}**. What is your **Industry**?")
                    st.session_state.step = 2
                    st.rerun()

    elif st.session_state.step == 2:
        with st.chat_message("assistant"):
            st.write("**Select Industry:**")
            industry = st.radio("Choose One:", INDUSTRY_OPTIONS, index=None, key="industry_radio")
            if industry:
                if st.button("Confirm Industry"):
                    st.session_state.data["industry"] = industry
                    add_msg("assistant", f"Industry: **{industry}**. Is your business Virtual or Physical?")
                    st.session_state.step = 3
                    st.rerun()

    elif st.session_state.step == 3:
        with st.chat_message("assistant"):
            st.write("**Is your business Virtual/Online or a Physical Shop?**")
            loc_type = st.radio("Select:", ["Virtual/Online", "Physical Shop"], index=None, key="loc_radio")
            if loc_type:
                st.session_state.data["location_type"] = loc_type
                add_msg("assistant", f"Selected: {loc_type}. **Do you already have a website?**")
                st.session_state.step = 4
                st.rerun()

    elif st.session_state.step == 4:
        with st.chat_message("assistant"):
            st.write("**Do you already have a website?**")
            has_web = st.radio("Select:", ["Yes", "No"], index=None, key="web_radio")
            if has_web:
                st.session_state.data["has_website"] = has_web
                if has_web == "Yes":
                    add_msg("assistant", "Please enter your **Website URL**.")
                    st.session_state.step = 4.1
                else:
                    st.session_state.data["website_url"] = "None"
                    add_msg("assistant", "No website yet. Is this an **eCommerce business?**")
                    st.session_state.step = 5
                st.rerun()

    elif st.session_state.step == 5:
        with st.chat_message("assistant"):
            st.write("**Is this an eCommerce business?**")
            is_ecom = st.radio("Select:", ["Yes", "No"], index=None, key="ecom_radio")
            if is_ecom:
                st.session_state.data["is_ecommerce"] = is_ecom
                add_msg("assistant", "Select up to 3 **Focus Areas**.")
                st.session_state.step = 7
                st.rerun()

    elif st.session_state.step == 7:
        with st.chat_message("assistant"):
            st.info("Select up to 3 Focus Areas:")
            options = ["Website", "eCommerce", "Proposals", "Marketing", "Analytics", "Growth"]
            selected = st.multiselect("Select:", options, key="focus_multi", max_selections=3)
            if st.button("Confirm Selection"):
                if len(selected) < 1:
                    st.error("Select at least 1.")
                else:
                    st.session_state.data["services"] = selected
                    add_msg("assistant", "Select your **Website Structure**.")
                    st.session_state.step = 8
                    st.rerun()

    elif st.session_state.step == 8:
        with st.chat_message("assistant"):
            st.write("**Select Website Structure:**")
            structure = st.radio("Choose One:", STRUCTURE_OPTIONS, index=None, key="structure_radio")
            if structure:
                if st.button("Confirm Structure"):
                    st.session_state.data["structure"] = structure
                    add_msg("assistant", f"Structure: **{structure}**. Select your **Business Model**.")
                    st.session_state.step = 9 
                    st.rerun()

    # --- STEP 9: BUSINESS MODEL ---
    elif st.session_state.step == 9:
        industry = st.session_state.data.get("industry", "Retail & Consumer Goods")
        relevant_models = INDUSTRY_TO_MODELS.get(industry, ["General Service", "General Product"])
        
        with st.chat_message("assistant"):
            st.write(f"**Select Specific Business Model for {industry}:**")
            model = st.selectbox("Choose Model:", relevant_models, index=None, placeholder="Select model...")
            
            if model:
                if st.button("Confirm Model"):
                    st.session_state.data["business_model"] = model
                    add_msg("assistant", f"Model: **{model}**. Let's configure your Attributes.")
                    st.session_state.step = 12
                    st.rerun()

    # --- STEP 12: ATTRIBUTES ---
    elif st.session_state.step == 12:
        model_key = st.session_state.data.get("business_model", "")
        industry = st.session_state.data.get("industry", "")
        
        # 1. Defaults
        if model_key in ATTRIBUTE_DEFAULTS:
            attr_options = ATTRIBUTE_DEFAULTS[model_key]
        else:
            attr_options = ATTRIBUTE_DEFAULTS["General Service"]

        # 2. Suggestion Pool
        suggestion_pool = get_suggestion_pool(model_key, industry)

        with st.chat_message("assistant"):
            if isinstance(attr_options, dict):
                st.write(f"**What type of {model_key}?**")
                sub_type = st.selectbox("Select Category:", list(attr_options.keys()))
                defaults = attr_options[sub_type]
            else:
                defaults = attr_options

            st.write(f"**Attribute Setup for {model_key}**")
            st.info(f"Core: {', '.join(defaults)}")
            
            st.write("Do you want to use this set or customize it?")
            choice = st.radio("Select:", ["Use Suggested", "Customize"], index=None, key="attr_radio")
            
            if choice == "Use Suggested":
                st.session_state.data["final_attributes"] = defaults
                add_msg("assistant", "Using default attributes. What is the **Product Name**?")
                st.session_state.step = 13
                st.rerun()
            elif choice == "Customize":
                # Combine defaults with specific pool ONLY.
                combined_options = list(set(defaults + suggestion_pool)) 
                
                st.write("**Add/Remove Attributes:**")
                final_attrs = st.multiselect("Select Attributes:", options=combined_options, default=defaults)
                if st.button("Confirm Custom Attributes"):
                    st.session_state.data["final_attributes"] = final_attrs
                    add_msg("assistant", "Attributes saved. What is the **Product Name**?")
                    st.session_state.step = 13
                    st.rerun()

    elif st.session_state.step == 15:
        with st.chat_message("assistant"):
            st.write("**Who is your Target Segment?**")
            segment = st.radio("Select One:", SEGMENT_OPTIONS, index=None, key="segment_radio")
            if segment:
                if st.button("Confirm & Generate"):
                    st.session_state.data["segment"] = segment
                    st.session_state.step = 20
                    st.rerun()

# --- UI: FINAL OUTPUT ---
elif st.session_state.step == 20:
    data = st.session_state.data
    
    # 1. GENERATION PHASE (Runs Once)
    if not st.session_state.generation_complete:
        st.info(f"⚡ Architecting {data.get('business_model')} Data & {data.get('structure')}...")
        manual_image_prompt = f"A photorealistic, 4k hero image for a {data.get('business_model')} business named {data['name']}. Context: {data['industry']}."
        
        with st.spinner(f"🤖 Coding {data.get('structure')} Website..."):
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_gpt = executor.submit(generate_business_package, api_key, selected_model, data)
                future_dalle = executor.submit(generate_dalle_image, api_key, manual_image_prompt)
                
                structure_res, used_prompt = future_gpt.result()
                dalle_url = future_dalle.result()

            if "error" in structure_res:
                st.error(f"GPT Error: {structure_res['error']}")
                with st.expander("Show Prompt"):
                    st.code(used_prompt)
                st.stop()
            
            # Inject Image
            final_pages = {}
            raw_pages = structure_res.get("ui_pages", {})
            for page_name, page_html in raw_pages.items():
                final_pages[page_name] = page_html.replace("HERO_IMAGE_PLACEHOLDER", dalle_url)
            
            st.session_state.result = {
                **structure_res,
                "ui_pages": final_pages,
                "generated_image_url": dalle_url
            }
            # MARK AS COMPLETE & SET SUCCESS FLAG
            st.session_state.generation_complete = True
            st.session_state.show_success = True
            st.rerun() # Strict rerun to clear loading UI

    # 2. RENDERING PHASE (Stable View)
    if st.session_state.generation_complete:
        # Show Banner Once
        if st.session_state.show_success:
            st.balloons()
            st.success("✅ BizOnboard Generation Complete!")
            st.session_state.show_success = False # Turn off for next render
        
        res = st.session_state.result
        pages = res.get("ui_pages", {})

        st.title(f"{data['name']} - {data.get('business_model')} Platform")

        tabs = st.tabs(["🖥️ Live Pages", "📦 Product Sets", "🔧 Attribute Sets", "📂 Categories", "📢 Banner", "💾 JSON Data", "📥 Download"])

        with tabs[0]:
            st.write("### Website Preview")
            if len(pages) > 1:
                page_selection = st.radio("Navigate Pages:", list(pages.keys()), horizontal=True)
                html_content = pages.get(page_selection, "<div>No content</div>")
            else:
                html_content = list(pages.values())[0] if pages else "<div>No content</div>"
            st.components.v1.html(html_content, height=800, scrolling=True)

        with tabs[1]:
            st.subheader("Generated Inventory Strategy")
            products = res.get("sample_products", [])
            if products:
                for p in products:
                    with st.expander(f"📦 {p.get('name')} ({p.get('price')})"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("#### Core Attributes")
                            st.json(p.get("attributes"))
                        with c2:
                            st.markdown("#### Pricing Rules")
                            st.dataframe(p.get("pricing_rules"))
                        st.markdown("#### Variants")
                        st.dataframe(p.get("variants"))
            else:
                st.warning("No products generated.")

        with tabs[2]:
            st.subheader("Attribute Definitions")
            attr_sets = res.get("attribute_sets", [])
            for aset in attr_sets:
                st.write(f"**Set Name:** {aset.get('name')}")
                st.table(aset.get("attributes"))

        with tabs[3]:
            st.subheader("Category Taxonomy")
            st.json(res.get("categories_tree"))

        with tabs[4]:
            st.write("### Marketing Banner")
            banner_html = res.get("marketing_banner_html", "<div>Banner Error</div>")
            st.components.v1.html(banner_html, height=400, scrolling=False)

        with tabs[5]:
            st.subheader("Complete JSON Response")
            st.json(res)

        with tabs[6]:
            st.subheader("📦 Download Complete Package")
            c1, c2 = st.columns(2)
            with c1:
                zip_data = create_zip(pages)
                st.download_button("Download Site (.zip)", zip_data, f"{data['name']}_site.zip", "application/zip")
            with c2:
                json_str = json.dumps(res, indent=2)
                st.download_button("Download Data (.json)", json_str, f"{data['name']}_data.json", "application/json")
