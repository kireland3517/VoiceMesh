"""Customer management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.api.database import get_db
from src.api.models import Customer
from src.api.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerList
)
from src.api.security import generate_api_key, hash_api_key, generate_customer_id

logger = structlog.get_logger()

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/", response_model=CustomerResponse, status_code=201)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new customer.

    Generates API key automatically and returns it.
    **Save the API key - it won't be shown again!**

    Args:
        customer_data: Customer information

    Returns:
        Customer with generated API key

    Raises:
        400: Email already exists
    """
    # Check if email already exists
    result = await db.execute(
        select(Customer).where(Customer.email == customer_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Generate API key and customer ID
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    customer_id = generate_customer_id()

    # Create customer
    customer = Customer(
        id=customer_id,
        name=customer_data.name,
        email=customer_data.email,
        phone=customer_data.phone,
        api_key=api_key,  # Store plain key temporarily for response
        api_key_hash=api_key_hash,
        default_voice=customer_data.default_voice,
        default_language=customer_data.default_language,
        notes=customer_data.notes,
    )

    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    logger.info(
        "customer_created",
        customer_id=customer.id,
        email=customer.email
    )

    return customer


@router.get("/", response_model=CustomerList)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all customers with pagination.

    Args:
        page: Page number (starting from 1)
        page_size: Number of customers per page (max 100)
        is_active: Filter by active status (optional)

    Returns:
        Paginated list of customers
    """
    # Build query
    query = select(Customer)
    if is_active is not None:
        query = query.where(Customer.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(Customer)
    if is_active is not None:
        count_query = count_query.where(Customer.is_active == is_active)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Customer.created_at.desc())

    result = await db.execute(query)
    customers = result.scalars().all()

    return CustomerList(
        customers=customers,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific customer by ID.

    Args:
        customer_id: Customer ID

    Returns:
        Customer details

    Raises:
        404: Customer not found
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a customer.

    Args:
        customer_id: Customer ID
        customer_data: Fields to update

    Returns:
        Updated customer

    Raises:
        404: Customer not found
        400: Email already exists (if changing email)
    """
    # Get customer
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check email uniqueness if changing email
    if customer_data.email and customer_data.email != customer.email:
        result = await db.execute(
            select(Customer).where(Customer.email == customer_data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

    # Update fields
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.commit()
    await db.refresh(customer)

    logger.info(
        "customer_updated",
        customer_id=customer.id,
        fields_updated=list(update_data.keys())
    )

    return customer


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a customer.

    This will also delete all associated functions and call records.

    Args:
        customer_id: Customer ID

    Raises:
        404: Customer not found
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    await db.delete(customer)
    await db.commit()

    logger.info(
        "customer_deleted",
        customer_id=customer_id
    )

    return None


@router.post("/{customer_id}/regenerate-api-key", response_model=CustomerResponse)
async def regenerate_api_key(
    customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Regenerate API key for a customer.

    **Save the new API key - it won't be shown again!**

    Args:
        customer_id: Customer ID

    Returns:
        Customer with new API key

    Raises:
        404: Customer not found
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Generate new API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    customer.api_key = api_key
    customer.api_key_hash = api_key_hash

    await db.commit()
    await db.refresh(customer)

    logger.info(
        "customer_api_key_regenerated",
        customer_id=customer.id
    )

    return customer
