import streamlit as st
import time
import json
import zipfile
import io
import concurrent.futures
from openai import OpenAI

# --- Configuration ---
st.set_page_config(page_title="BizOnboard Builder", page_icon="🚀", layout="wide")

# --- Custom CSS ---
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
    
    /* JSON Styling */
    div[data-testid="stJson"] {
        background-color: #151922; padding: 20px; border-radius: 10px; border: 1px solid #334155;
        white-space: pre-wrap; word-wrap: break-word; overflow-x: auto;
    }

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
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your BizOnboard Builder.\n\nLet's build a complete **Data-Driven Digital Presence**. First, what is your **Business Name**?"}]

# --- CONSTANTS ---
BUSINESS_TYPES = [
    "Service-Based Business",
    "Professional Service Business",
    "E-commerce Store",
    "Product-Based Business",
    "Asset / Transaction-Based Business",
    "Digital Product / Service Business"
]

INDUSTRY_OPTIONS = [
    "Architecture & Design",
    "Hospitality & Tourism",
    "Real Estate & Property Development",
    "Healthcare & Medical Services",
    "Retail & Consumer Goods"
    
]

THEME_OPTIONS = [
    "Modern & Minimal", "Luxury & Premium", "Bold & Creative", 
    "Corporate & Professional", "Friendly & Playful", "Tech & Futuristic", 
    "Nature & Organic", "Content-First / Editorial", 
    "E-commerce & Sales Focused"
]

STRUCTURE_OPTIONS = ["Single Page", "Multi Page", "Landing Page"]

SEGMENT_OPTIONS = [
    "B2C (Individual Consumers)",
    "B2B (Businesses / Companies)",
    "B2B2C (Businesses serving end customers)",
    "D2C (Direct to Consumer)",
    "Niche / Enthusiast Audience"
]

ATTRIBUTE_DEFAULTS = {
    "eCommerce Product": ["Size", "Color", "Material", "Fit", "Brand"],
    "Hotel / Accommodation": ["Room Type", "Bed Type", "View", "Amenities", "Meal Plan"],
    "Travel Package": ["Duration", "Destination", "Inclusions", "Hotel Category"],
    "Rental Product": ["Duration Unit", "Deposit", "Condition", "Usage Limits"],
    "Service": ["Duration", "Location", "Level", "Provider Type"]
}

# --- HELPER FUNCTIONS ---
def create_zip(pages_dict):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_title, html_content in pages_dict.items():
            if page_title.lower() == "home":
                filename = "index.html"
            else:
                filename = f"{page_title.lower().replace(' ', '_')}.html"
            zip_file.writestr(filename, html_content)
    return zip_buffer.getvalue()

def generate_dalle_image(image_prompt):
    client = OpenAI(api_key=api_key)
    try:
        response = client.images.generate(
            model="dall-e-3", prompt=image_prompt, size="1024x1024", quality="standard", n=1
        )
        return response.data[0].url
    except Exception:
        return "https://placehold.co/1024x1024/222/FFF?text=Image+Generation+Error"

def generate_business_package(model_name, data):
    client = OpenAI(api_key=api_key)
    
    model_type = data.get('business_model', 'General')
    structure = data.get('structure', 'Single Page')
    attributes_final = ", ".join(data.get('final_attributes', []))
    
    # --- STRICT STRUCTURE LOGIC ---
    if structure == "Single Page":
        structure_rules = """
        TYPE: Single Page Application (SPA).
        NAVIGATION: Use anchor links (e.g., href='#services') connecting to section IDs.
        LAYOUT: All content (Home, About, Services, Contact) must be vertically stacked on this one page.
        """
        json_hint = '"ui_pages": { "Home": "Full HTML5 string for index.html..." }'
    elif structure == "Multi Page":
        structure_rules = """
        TYPE: Multi-Page Website.
        NAVIGATION: Use standard file links (e.g., href='about.html', href='contact.html').
        LAYOUT: The Home page should serve as a 'Hub' or 'Gateway', summarizing content and linking outward.
        Create separate HTML strings for Home, About, Services, Contact.
        """
        json_hint = '"ui_pages": { "Home": "<html>...", "About": "<html>...", "Services": "<html>...", "Contact": "<html>..." }'
    else: # Landing Page
        structure_rules = """
        TYPE: Landing Page.
        NAVIGATION: Minimal or Hidden. Focus on conversion.
        LAYOUT: Strong Hero Section -> Social Proof -> Features -> Call To Action (CTA). No distractions.
        """
        json_hint = '"ui_pages": { "Home": "Full HTML5 string for index.html..." }'

    prompt = f"""
    You are a Data Architect and World-Class UI/UX Designer.
    
    Client Context:
    - Name: {data.get('name')}
    - Model: {model_type}
    - Structure: {structure}
    - Theme: {data.get('theme')}
    - Focus: {", ".join(data.get('services', []))}
    - Product: {data.get('prod_name')}
    - Attributes: {attributes_final}
    
    TASK 1: Generate Data (JSON).
    TASK 2: Generate Website Structure.
    
    *** STRICT RULES FOR '{structure}' ***
    {structure_rules}
    
    OUTPUT JSON STRUCTURE (Strict):
    {{
        "business_details": {{ "name": "String", "model": "{model_type}", "structure": "{structure}" }},
        "categories_tree": [ {{ "id": 1, "name": "{data.get('main_cat')}", "children": [ {{ "id": 2, "name": "{data.get('sub_cat')}" }} ] }} ],
        "attribute_sets": [ {{ "name": "Custom Set", "attributes": {json.dumps(data.get('final_attributes', []))} }} ],
        "sample_products": [
            {{
                "id": "P001", "name": "{data.get('prod_name')}", "description": "{data.get('prod_desc')}", "price": 100,
                "attributes": {{ "Attr": "Val" }}, "variants": [ {{ "sku": "V1", "spec": "Var1", "stock": 10 }} ],
                "pricing_rules": [ {{ "name": "Rule", "rule": "Desc" }} ]
            }}
        ],
        "marketing_banner_html": "<div>...</div>",
        {json_hint}
    }}
    Constraints: Return ONLY raw JSON. No markdown. Do not add explanations.
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
    elif step == 10:
        data["main_cat"] = text
        add_msg("assistant", "Do you want to add a **Sub-category**? (e.g. Men > T-Shirts)")
        st.session_state.step = 11
    elif step == 11:
        data["sub_cat"] = text
        st.session_state.step = 12
    elif step == 13:
        data["prod_name"] = text
        add_msg("assistant", "Give a **Short Description** of the product.")
        st.session_state.step = 14
    elif step == 14:
        data["prod_desc"] = text
        st.session_state.step = 15

# --- UI: SIDEBAR ---
with st.sidebar:
    st.title("💎 Design Config")
    
    if st.button("Restart", type="primary"):
        st.session_state.clear()
        st.rerun()
    
    st.markdown("### Select Model")
    valid_models = ["gpt-4o", "gpt-4.1", "gpt-5-chat-latest", "gpt-5"]
    selected_model = st.selectbox("Model Name", valid_models, index=0)

# --- UI: CHAT ---
if st.session_state.step <= 15:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    text_steps = [0, 4.1, 10, 11, 13, 14]
    if st.session_state.step in text_steps:
        if prompt := st.chat_input("Type answer..."):
            with st.chat_message("user"):
                st.markdown(prompt)
            add_msg("user", prompt)
            time.sleep(0.2)
            process_input(prompt)
            st.rerun()

    elif st.session_state.step == 1:
        with st.chat_message("assistant"):
            st.write("**Select Business Type:**")
            b_type = st.radio("Choose One:", BUSINESS_TYPES, index=None, key="type_radio")
            if b_type:
                if st.button("Confirm Type"):
                    st.session_state.data["type"] = b_type
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
                add_msg("assistant", "Select your **Theme & Vibe**:")
                st.session_state.step = 6
                st.rerun()

    elif st.session_state.step == 6:
        with st.chat_message("assistant"):
            st.write("**Choose one style:**")
            theme = st.radio("Select Theme:", THEME_OPTIONS, index=None, key="theme_radio")
            if theme:
                st.session_state.data["theme"] = theme
                add_msg("assistant", f"Theme: **{theme}**. Select up to 3 **Focus Areas**.")
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
                    add_msg("assistant", f"Structure: **{structure}**. Now select your **Business Model**.")
                    st.session_state.step = 9
                    st.rerun()

    elif st.session_state.step == 9:
        with st.chat_message("assistant"):
            st.write("**Select Business Model:**")
            models = ["eCommerce Product", "Hotel / Accommodation", "Travel Package", "Rental Product", "Service"]
            model = st.selectbox("Choose Model:", models, index=None, placeholder="Select model...")
            if model:
                if st.button("Confirm Model"):
                    st.session_state.data["business_model"] = model
                    add_msg("assistant", f"Model: **{model}**. What is your **Main Category**?")
                    st.session_state.step = 10
                    st.rerun()

    elif st.session_state.step == 12:
        model = st.session_state.data["business_model"]
        defaults = ATTRIBUTE_DEFAULTS.get(model, [])
        with st.chat_message("assistant"):
            st.write(f"**Attribute Setup for {model}**")
            st.info(f"Suggested: {', '.join(defaults)}")
            st.write("Do you want to use this set or customize it?")
            choice = st.radio("Select:", ["Use Suggested", "Customize"], index=None, key="attr_radio")
            
            if choice == "Use Suggested":
                st.session_state.data["final_attributes"] = defaults
                add_msg("assistant", "Using default attributes. What is the **Product Name**?")
                st.session_state.step = 13
                st.rerun()
            elif choice == "Customize":
                final_attrs = st.multiselect("Modify Attributes:", defaults + ["Weight", "Gender", "Warranty", "Expiry"], default=defaults)
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
    
    if "result" not in st.session_state:
        st.info(f"⚡ Architecting {data['business_model']} Data & {data.get('structure')}...")
        
        manual_image_prompt = f"A photorealistic, 4k hero image for a {data['business_model']} business named {data['name']}. Theme: {data['theme']}."
        
        with st.spinner(f"🤖 Defining Attributes & Coding Website..."):
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_gpt = executor.submit(generate_business_package, selected_model, data)
                future_dalle = executor.submit(generate_dalle_image, manual_image_prompt)
                
                structure_res, used_prompt = future_gpt.result()
                dalle_url = future_dalle.result()

            if "error" in structure_res:
                st.error(f"GPT Error: {structure_res['error']}")
                with st.expander("Show Prompt"):
                    st.code(used_prompt)
                st.stop()
            
            st.session_state.structure_res = structure_res
            st.session_state.used_prompt = used_prompt
            st.session_state.dalle_url = dalle_url

        # Inject Image into Pages
        final_pages = {}
        raw_pages = st.session_state.structure_res.get("ui_pages", {})
        
        for page_name, page_html in raw_pages.items():
            final_pages[page_name] = page_html.replace("HERO_IMAGE_PLACEHOLDER", st.session_state.dalle_url)
        
        st.session_state.result = {
            **st.session_state.structure_res,
            "ui_pages": final_pages,
            "generated_image_url": st.session_state.dalle_url
        }

    res = st.session_state.result
    pages = res.get("ui_pages", {})

    st.balloons()
    st.success("✅ BizOnboard Generation Complete!")
    st.title(f"{data['name']} - {data['business_model']} Platform")

    # --- TABS ---
    tabs = st.tabs([
        "🖥️ Live Pages", "📦 Product Sets", "🔧 Attribute Sets", "📂 Categories", 
        "📢 Banner", "💾 JSON Data", "📥 Download"
    ])

    # 1. LIVE PAGES
    with tabs[0]:
        st.write("### Website Preview")
        if len(pages) > 1:
            page_selection = st.radio("Navigate Pages:", list(pages.keys()), horizontal=True)
            html_content = pages.get(page_selection, "<div>No content</div>")
        else:
            html_content = list(pages.values())[0] if pages else "<div>No content</div>"
            
        st.components.v1.html(html_content, height=800, scrolling=True)

    # 2. PRODUCT SETS
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

    # 3. ATTRIBUTE SETS
    with tabs[2]:
        st.subheader("Attribute Definitions")
        attr_sets = res.get("attribute_sets", [])
        for aset in attr_sets:
            st.write(f"**Set Name:** {aset.get('name')}")
            st.table(aset.get("attributes"))

    # 4. CATEGORIES
    with tabs[3]:
        st.subheader("Category Taxonomy")
        st.json(res.get("categories_tree"))

    # 5. BANNER
    with tabs[4]:
        st.write("### Marketing Banner")
        banner_html = res.get("marketing_banner_html", "<div>Banner Error</div>")
        st.components.v1.html(banner_html, height=400, scrolling=False)

    # 6. JSON DATA
    with tabs[5]:
        st.subheader("Complete JSON Response")
        st.json(res)

    # 7. DOWNLOAD
    with tabs[6]:
        st.subheader("📦 Download Complete Package")
        c1, c2 = st.columns(2)
        with c1:
            zip_data = create_zip(pages)
            st.download_button("Download Site (.zip)", zip_data, f"{data['name']}_site.zip", "application/zip")
        with c2:
            json_str = json.dumps(res, indent=2)
            st.download_button("Download Data (.json)", json_str, f"{data['name']}_data.json", "application/json")
