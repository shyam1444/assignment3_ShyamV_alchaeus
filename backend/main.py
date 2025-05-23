import os
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import firebase_admin
from firebase_admin import credentials, firestore, storage
import json

# Initialize Firebase Admin
cred = credentials.Certificate("assignment3-2865c-63775c0b75a2.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "https://lucky-moonbeam-f4a2f3.netlify.app"  # Your Netlify URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Firebase Storage bucket
BUCKET_NAME = os.environ.get('FIREBASE_STORAGE_BUCKET', 'assignment3-2865c.appspot.com') # Replace with your default bucket name if different
bucket = storage.bucket(name=BUCKET_NAME)

class LeadCreate(BaseModel):
    name: str
    contact: str
    company: Optional[str] = None
    product_interest: Optional[str] = None
    stage: str = "New"
    follow_up_date: Optional[str] = None
    notes: Optional[str] = None
    documents: List[str] = []

class LeadUpdateStage(BaseModel):
    stage: str

class Lead(BaseModel):
    id: str
    name: str
    contact: str
    company: Optional[str] = None
    product_interest: Optional[str] = None
    stage: str
    follow_up_date: Optional[str] = None
    notes: Optional[str] = None
    documents: List[str] = []

class OrderCreate(BaseModel):
    lead_id: str
    status: str = "Order Received"
    dispatch_date: Optional[str] = None
    tracking_info: Optional[str] = None
    documents: List[str] = []

class OrderUpdateStatus(BaseModel):
    status: str

class Order(BaseModel):
    id: str
    lead_id: str
    status: str
    dispatch_date: Optional[str] = None
    tracking_info: Optional[str] = None
    documents: List[str] = []

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/leads", response_model=Lead)
def create_lead(lead: LeadCreate):
    lead_dict = lead.model_dump()
    # Remove id if present, as Firestore generates it
    lead_dict.pop('id', None)
    doc_ref = db.collection("leads").document()
    doc_ref.set(lead_dict)
    created_lead = lead_dict
    created_lead["id"] = doc_ref.id
    return created_lead 

@app.put("/leads/{lead_id}", response_model=Lead)
def update_lead(lead_id: str, lead_update: LeadCreate):
    doc_ref = db.collection("leads").document(lead_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Update the lead with the new data
    update_data = lead_update.model_dump(exclude_unset=True)
    doc_ref.update(update_data)

    # Get the updated document
    updated_doc = doc_ref.get()
    updated_lead_data = updated_doc.to_dict()
    updated_lead_data["id"] = updated_doc.id
    return updated_lead_data

@app.get("/leads", response_model=List[Lead])
def get_leads(stage: Optional[str] = None, follow_up_date: Optional[str] = None):
    leads_ref = db.collection("leads")
    query = leads_ref

    if stage:
        query = query.where("stage", "==", stage)
    if follow_up_date:
        # Note: Filtering by date range might require a different approach depending on how date is stored (timestamp vs string)
        # This basic implementation assumes exact string match for simplicity
        query = query.where("follow_up_date", "==", follow_up_date)

    docs = query.stream()
    leads = []
    for doc in docs:
        lead_data = doc.to_dict()
        lead_data["id"] = doc.id
        leads.append(Lead(**lead_data))
    return leads 

@app.post("/orders", response_model=Order)
def create_order(order: OrderCreate):
    order_dict = order.model_dump()
    doc_ref = db.collection("orders").document()
    doc_ref.set(order_dict)
    created_order = order_dict
    created_order["id"] = doc_ref.id
    return created_order 

@app.put("/orders/{order_id}", response_model=Order)
def update_order(order_id: str, order_update: OrderCreate): # Use OrderCreate model for incoming data
    doc_ref = db.collection("orders").document(order_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Order not found")

    # Prepare data for update, excluding the id which is not updatable this way
    update_data = order_update.model_dump(exclude_unset=True) # Use exclude_unset to only update provided fields
    
    doc_ref.update(update_data)

    # Fetch the updated document to return the full Order object
    updated_doc = doc_ref.get()
    updated_order_data = updated_doc.to_dict()
    updated_order_data["id"] = updated_doc.id

    return updated_order_data

@app.put("/orders/{order_id}/status", response_model=Order)
def update_order_status(order_id: str, status_update: OrderUpdateStatus):
    doc_ref = db.collection("orders").document(order_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Order not found")

    doc_ref.update({"status": status_update.status})
    updated_order_data = doc.to_dict()
    updated_order_data["status"] = status_update.status # Update locally for response
    updated_order_data["id"] = doc.id
    return updated_order_data 

@app.get("/orders", response_model=List[Order])
def get_orders(lead_id: Optional[str] = None):
    orders_ref = db.collection("orders")
    query = orders_ref

    if lead_id:
        query = query.where("lead_id", "==", lead_id)

    docs = query.stream()
    orders = []
    for doc in docs:
        order_data = doc.to_dict()
        order_data["id"] = doc.id
        orders.append(Order(**order_data))
    return orders 

@app.get("/metrics/leads")
def get_lead_metrics():
    total_leads = db.collection("leads").stream()
    total_count = sum(1 for _ in total_leads) # Consume iterator to get count

    leads_by_stage = {}
    for stage in ["New", "Contacted", "Qualified", "Proposal Sent", "Won", "Lost"]:
        count = db.collection("leads").where("stage", "==", stage).stream()
        leads_by_stage[stage] = sum(1 for _ in count)

    return {
        "total_leads": total_count,
        "leads_by_stage": leads_by_stage
    } 

@app.get("/metrics/orders")
def get_order_metrics():
    total_orders = db.collection("orders").stream()
    total_count = sum(1 for _ in total_orders)  # Consume iterator to get count

    orders_by_status = {}
    for status in ["Order Received", "In Development", "Ready to Dispatch", "Dispatched"]:
        count = db.collection("orders").where("status", "==", status).stream()
        orders_by_status[status] = sum(1 for _ in count)

    return {
        "total_orders": total_count,
        "orders_by_status": orders_by_status
    } 

@app.get("/leads/followup", response_model=List[Lead])
def get_leads_for_followup():
    # This currently returns all leads with a follow_up_date set.
    # More advanced filtering (e.g., overdue dates) would require date comparison logic.
    leads_ref = db.collection("leads")
    query = leads_ref.where("follow_up_date", "!=", None)

    docs = query.stream()
    followup_leads = []
    for doc in docs:
        lead_data = doc.to_dict()
        lead_data["id"] = doc.id
        followup_leads.append(Lead(**lead_data))
    return followup_leads 

@app.delete("/leads/{lead_id}")
def delete_lead(lead_id: str):
    doc_ref = db.collection("leads").document(lead_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Lead not found")

    doc_ref.delete()
    return {"message": f"Lead with ID {lead_id} deleted successfully"}

@app.delete("/orders/{order_id}")
def delete_order(order_id: str):
    doc_ref = db.collection("orders").document(order_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Order not found")

    doc_ref.delete()
    return {"message": f"Order with ID {order_id} deleted successfully"}

@app.post("/upload_document")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    document_id: str = Form(...)
):
    try:
        # Create a unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{document_type}/{document_id}/{file.filename}"
        
        # Upload to Firebase Storage
        blob = bucket.blob(unique_filename)
        blob.upload_from_file(file.file)
        
        # Get the public URL
        blob.make_public()
        file_url = blob.public_url
        
        # Update the document in Firestore
        if document_type == "lead":
            doc_ref = db.collection("leads").document(document_id)
        elif document_type == "order":
            doc_ref = db.collection("orders").document(document_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid document type")
            
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"{document_type.capitalize()} not found")
            
        # Update the documents array
        current_data = doc.to_dict()
        documents = current_data.get("documents", [])
        documents.append(file_url)
        doc_ref.update({"documents": documents})
        
        return {"message": "File uploaded successfully", "file_url": file_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/delete_document")
async def delete_document(document_type: str, document_id: str, file_path: str):
    try:
        # Delete from Firebase Storage
        blob = bucket.blob(file_path)
        blob.delete()
        
        # Update the document in Firestore
        if document_type == "lead":
            doc_ref = db.collection("leads").document(document_id)
        elif document_type == "order":
            doc_ref = db.collection("orders").document(document_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid document type")
            
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"{document_type.capitalize()} not found")
            
        # Update the documents array
        current_data = doc.to_dict()
        documents = current_data.get("documents", [])
        documents = [doc for doc in documents if doc != file_path]
        doc_ref.update({"documents": documents})
        
        return {"message": "File deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/leads/{lead_id}/stage", response_model=Lead)
def update_lead_stage(lead_id: str, stage_update: LeadUpdateStage):
    doc_ref = db.collection("leads").document(lead_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Lead not found")

    doc_ref.update({"stage": stage_update.stage})

    # If the lead stage is updated to "Won", create a new order
    if stage_update.stage == "Won":
        order_data = {
            "lead_id": lead_id,
            "status": "Order Received"  # Default status for a new order from a won lead
        }
        db.collection("orders").document().set(order_data)

    updated_lead_data = doc.to_dict()
    updated_lead_data["stage"] = stage_update.stage  # Update locally for response
    updated_lead_data["id"] = doc.id
    return updated_lead_data 