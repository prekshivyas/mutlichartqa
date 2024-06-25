import streamlit as st
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from PIL import Image
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Set page configuration
st.set_page_config(layout="wide")


firebase_credentials = {
    "type": st.secrets["FIREBASE_TYPE"],
    "project_id": st.secrets["FIREBASE_PROJECT_ID"],
    "private_key_id": st.secrets["FIREBASE_PRIVATE_KEY_ID"],
    "private_key": st.secrets["FIREBASE_PRIVATE_KEY"],
    "client_email": st.secrets["FIREBASE_CLIENT_EMAIL"],
    "client_id": st.secrets["FIREBASE_CLIENT_ID"],
    "auth_uri": st.secrets["FIREBASE_AUTH_URI"],
    "token_uri": st.secrets["FIREBASE_TOKEN_URI"],
    "auth_provider_x509_cert_url": st.secrets["FIREBASE_AUTH_PROVIDER_X509_CERT_URL"],
    "client_x509_cert_url": st.secrets["FIREBASE_CLIENT_X509_CERT_URL"],
    "universe_domain": st.secrets["FIREBASE_UNIVERSE_DOMAIN"]
}


google_credentials = {
    "type": st.secrets["GOOGLE_TYPE"],
    "project_id": st.secrets["GOOGLE_PROJECT_ID"],
    "private_key_id": st.secrets["GOOGLE_PRIVATE_KEY_ID"],
    "private_key": st.secrets["GOOGLE_PRIVATE_KEY"],
    "client_email": st.secrets["GOOGLE_CLIENT_EMAIL"],
    "client_id": st.secrets["GOOGLE_CLIENT_ID"],
    "auth_uri": st.secrets["GOOGLE_AUTH_URI"],
    "token_uri": st.secrets["GOOGLE_TOKEN_URI"],
    "auth_provider_x509_cert_url": st.secrets["GOOGLE_AUTH_PROVIDER_X509_CERT_URL"],
    "client_x509_cert_url": st.secrets["GOOGLE_CLIENT_X509_CERT_URL"],
    "universe_domain": st.secrets["GOOGLE_UNIVERSE_DOMAIN"]
}


dbURL = st.secrets["DB_URL"]

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred, {
        'databaseURL': dbURL
    })

# Google Drive API credentials setup
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

credentials = service_account.Credentials.from_service_account_info(
    google_credentials, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Initialize SessionState
if 'qa_pairs' not in st.session_state:
    st.session_state.qa_pairs = {}
if 'selected_category' not in st.session_state:
    st.session_state.selected_category = None
if 'images_displayed' not in st.session_state:
    st.session_state.images_displayed = False
if 'chart_id' not in st.session_state:
    st.session_state.chart_id = ""
if 'categories_submitted' not in st.session_state:
    st.session_state.categories_submitted = set()
if 'all_categories_submitted' not in st.session_state:
    st.session_state.all_categories_submitted = False

def save_qa_pairs(chart_id, category, qa_pairs):
    """Save QA pairs to Firebase Realtime Database"""
    root_ref = db.reference()
    
    # Create the basic structure if it doesn't exist
    chart_data = root_ref.child('charts').child(chart_id).get()
    if not chart_data:
        root_ref.child('charts').child(chart_id).set({
            'categories': {}
        })
    
    category_ref = root_ref.child(f'charts/{chart_id}/categories/{category}')
    
    # Update the database with the new QA pairs, overriding any existing pairs
    try:
        category_ref.set(qa_pairs)
        return True, "QA pairs added successfully"
    except Exception as e:
        print(f"Error saving QA pairs: {e}")
        return False, f"Error saving QA pairs: {str(e)}"

def get_qa_pairs(chart_id):
    """Retrieve all QA pairs for a given chart ID"""
    ref = db.reference(f'charts/{chart_id}')
    return ref.get()

# Google Drive functions
@st.cache_data
def get_folder_id(parent_folder_id, folder_name):
    results = drive_service.files().list(
        q=f"'{parent_folder_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
        spaces='drive', 
        fields='nextPageToken, files(id, name)'
    ).execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

@st.cache_data
def list_files_in_folder(folder_id):
    query = f"'{folder_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    return results.get('files', [])

@st.cache_data
def download_image(file_id, file_name):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = io.BytesIO(request.execute())
    return Image.open(downloader)

# Function to handle displaying of images
def display_images(chart_id):
    images_final_id = '11Ewq0e2Z7j4MkbLcuXWTUItL3DlCi5JB'
    anchor_chart_id = get_folder_id(images_final_id, f'anchor_{chart_id}')
    similar_chart_id = get_folder_id(images_final_id, f'anchor_{chart_id}_0')
    ids_to_display = [anchor_chart_id, similar_chart_id]

    if anchor_chart_id and similar_chart_id:
        st.subheader("MultiChartPair")
        for idx, folder_id in enumerate(ids_to_display):
            files = list_files_in_folder(folder_id)
            if files:
                st.subheader(f"Chart {idx + 1}:")
                for file in files:
                    if file['mimeType'] == 'image/png':
                        image = download_image(file['id'], file['name'])
                        st.image(image, caption=file['name'], use_column_width=True)
            else:
                st.warning(f"No files found in Folder {idx + 1}.")
    else:
        st.warning("One or both folder IDs not found. Please check your folder names.")

# Function to update QA pairs
def update_qa_pairs(selected_category):
    if selected_category not in st.session_state.qa_pairs:
        st.session_state.qa_pairs[selected_category] = []
    if len(st.session_state.qa_pairs[selected_category]) < 2:
        st.session_state.qa_pairs[selected_category].append({"question": "", "answer": ""})
    else:
        st.warning(f"Maximum 2 QA pairs allowed per category.")

# Function to submit the selected category
def submit_category():
    category = st.session_state.selected_category
    chart_id = st.session_state.chart_id

    if not chart_id:
        st.error("Chart ID cannot be empty.")
        return
    if not category:
        st.error("Category cannot be empty.")
        return

    qa_pairs = [{"question": qa["question"], "answer": qa["answer"]} for qa in st.session_state.qa_pairs[category] if qa["question"] and qa["answer"]]
    
    if qa_pairs:
        success, message = save_qa_pairs(chart_id, category, qa_pairs)
        if success:
            st.success(f"QA pairs saved for category: {category}")
        else:
            st.error(message)
    
    st.session_state.categories_submitted.add(category)

    # # Clear QA pairs for the selected category
    # if category in st.session_state.qa_pairs:
    #     del st.session_state.qa_pairs[category]

# Function to check if all categories are submitted
def check_all_categories_submitted():
    required_categories = {
        "Abstract Numerical Analysis", 
        "Entity Inference", 
        "Reasoning with Range Estimation"
    }
    st.session_state.all_categories_submitted = st.session_state.categories_submitted == required_categories

# Main UI layout
st.title("MultiChart QA Generation")
st.markdown("Instructions and Examples: [Click here](https://google.com)")

# Sidebar for Category Selection and QA Pair Management
with st.sidebar:
    selected_category = st.selectbox("Category", [
        "Abstract Numerical Analysis", 
        "Entity Inference", 
        "Reasoning with Range Estimation"
    ], key="category_select")

    # Update selected category in session state
    st.session_state.selected_category = selected_category

    # Add QA Pair button
    if st.button('Add QA Pair'):
        update_qa_pairs(selected_category)

    # Display QA pairs text boxes
    if selected_category in st.session_state.qa_pairs:
        for i, qa_pair in enumerate(st.session_state.qa_pairs[selected_category]):
            st.write(f"{selected_category} - Question {i + 1}")
            question_key = f"{selected_category.lower().replace(' ', '_')}_question_{i}"
            answer_key = f"{selected_category.lower().replace(' ', '_')}_answer_{i}"
            qa_pair["question"] = st.text_area(f"{selected_category} - Question {i + 1}", value=qa_pair.get("question", ""), key=question_key)
            qa_pair["answer"] = st.text_area(f"{selected_category} - Answer {i + 1}", value=qa_pair.get("answer", ""), key=answer_key)

            if i == 1:
                st.warning("You can only add up to 2 QA pairs.")

    # Submit Category button
    enable_submit_category = st.session_state.selected_category and any(qa_pair["question"] and qa_pair["answer"] for qa_pair in st.session_state.qa_pairs.get(selected_category, []))
    if st.button("Submit Category", disabled=not enable_submit_category):
        submit_category()

    # Submit All Categories button
    required_categories = {"Abstract Numerical Analysis", "Entity Inference", "Reasoning with Range Estimation"}
    if st.button("Submit All Categories", disabled=st.session_state.categories_submitted < required_categories):
        check_all_categories_submitted()
        if st.session_state.all_categories_submitted:
            st.success(f"All categories submitted successfully for Chart ID: {st.session_state.chart_id}!")
            saved_data = get_qa_pairs(st.session_state.chart_id)
            st.json(saved_data)
            # Reset state
            st.session_state.qa_pairs = {}
            st.session_state.selected_category = None
            st.session_state.images_displayed = False
            st.session_state.chart_id = ""
            st.session_state.categories_submitted = set()
            st.session_state.all_categories_submitted = False
        else:
            st.warning("Please ensure all categories have at least one QA pair added before submitting.")

# Display images based on input ID
chart_id = st.text_input("Enter Chart ID (0 to 100)", st.session_state.chart_id)
if st.button("Display"):
    st.session_state.chart_id = chart_id
    st.session_state.images_displayed = True

if st.session_state.images_displayed and st.session_state.chart_id:
    display_images(st.session_state.chart_id)
