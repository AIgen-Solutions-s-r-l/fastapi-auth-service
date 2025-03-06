"""
Stripe Products Retrieval Example

This script demonstrates how to retrieve products and their IDs from Stripe.
It showcases various filtering options and data extraction techniques.
"""

import asyncio
import os
import stripe
from datetime import datetime, UTC
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# Load environment variables from .env file
load_dotenv()

# Configure Stripe with API key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
stripe.api_version = os.getenv("STRIPE_API_VERSION", "2023-10-16")


async def list_all_products(limit: int = 100, active_only: bool = True) -> List[Dict[str, Any]]:
    """
    Retrieve all products from Stripe.
    
    Args:
        limit: Maximum number of products to retrieve
        active_only: If True, only retrieve active products
        
    Returns:
        List of product objects with simplified data
    """
    try:
        # Retrieve products from Stripe
        products = await asyncio.to_thread(
            stripe.Product.list,
            limit=limit,
            active=active_only
        )
        
        # Extract relevant information
        simplified_products = []
        for product in products.data:
            simplified_products.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "active": product.active,
                "created": datetime.fromtimestamp(product.created, UTC),
                "metadata": product.metadata,
                "url": product.url,
                "images": product.images
            })
        
        return simplified_products
        
    except Exception as e:
        print(f"Error retrieving products: {str(e)}")
        return []


async def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific product by its ID.
    
    Args:
        product_id: The Stripe product ID
        
    Returns:
        Product object if found, None otherwise
    """
    try:
        # Retrieve the specific product
        product = await asyncio.to_thread(
            stripe.Product.retrieve,
            product_id
        )
        
        # Return simplified product data
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "active": product.active,
            "created": datetime.fromtimestamp(product.created, UTC),
            "metadata": product.metadata,
            "url": product.url,
            "images": product.images
        }
        
    except Exception as e:
        print(f"Error retrieving product {product_id}: {str(e)}")
        return None


async def search_products_by_name(name_query: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Search for products by name using Stripe's search API.
    
    Args:
        name_query: Name to search for
        limit: Maximum number of results to return
        
    Returns:
        List of matching products
    """
    try:
        # Use Stripe's search API to find products
        search_results = await asyncio.to_thread(
            stripe.Product.search,
            query=f"name~'{name_query}'",
            limit=limit
        )
        
        # Extract relevant information
        simplified_products = []
        for product in search_results.data:
            simplified_products.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "active": product.active,
                "created": datetime.fromtimestamp(product.created, UTC)
            })
        
        return simplified_products
        
    except Exception as e:
        print(f"Error searching products: {str(e)}")
        return []


async def filter_products_by_metadata(key: str, value: str) -> List[Dict[str, Any]]:
    """
    Filter products by a specific metadata key-value pair.
    
    Args:
        key: Metadata key to filter by
        value: Metadata value to match
        
    Returns:
        List of products with matching metadata
    """
    try:
        # First retrieve all products
        all_products = await list_all_products(limit=100)
        
        # Filter products by metadata
        filtered_products = []
        for product in all_products:
            metadata = product.get("metadata", {})
            if metadata.get(key) == value:
                filtered_products.append(product)
        
        return filtered_products
        
    except Exception as e:
        print(f"Error filtering products: {str(e)}")
        return []


async def get_product_prices(product_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all prices associated with a specific product.
    
    Args:
        product_id: The Stripe product ID
        
    Returns:
        List of price objects for the product
    """
    try:
        # Retrieve prices for the product
        prices = await asyncio.to_thread(
            stripe.Price.list,
            product=product_id,
            active=True
        )
        
        # Extract relevant information
        simplified_prices = []
        for price in prices.data:
            amount = price.unit_amount / 100 if price.unit_amount else 0
            simplified_prices.append({
                "id": price.id,
                "amount": amount,
                "currency": price.currency,
                "recurring": price.recurring is not None,
                "recurring_interval": price.recurring.interval if price.recurring else None,
                "product_id": product_id,
                "active": price.active,
                "created": datetime.fromtimestamp(price.created, UTC)
            })
        
        return simplified_prices
        
    except Exception as e:
        print(f"Error retrieving prices for product {product_id}: {str(e)}")
        return []


async def display_product_summary(product_ids: Optional[List[str]] = None):
    """
    Display a summary of products with their IDs and other information.
    
    Args:
        product_ids: Optional list of specific product IDs to display.
                     If None, displays all active products.
    """
    try:
        if product_ids:
            # Retrieve specific products
            products = []
            for product_id in product_ids:
                product = await get_product_by_id(product_id)
                if product:
                    products.append(product)
        else:
            # Retrieve all active products
            products = await list_all_products()
        
        # Display product summary
        print(f"\n=== Product Summary ({len(products)} products) ===")
        for i, product in enumerate(products, 1):
            print(f"{i}. ID: {product['id']}")
            print(f"   Name: {product['name']}")
            print(f"   Description: {product['description'] or 'N/A'}")
            print(f"   Active: {product['active']}")
            print(f"   Created: {product['created']}")
            
            # Get prices for the product
            prices = await get_product_prices(product['id'])
            if prices:
                print(f"   Prices ({len(prices)}):")
                for price in prices:
                    recurring_info = ""
                    if price['recurring']:
                        recurring_info = f", {price['recurring_interval']} recurring"
                    print(f"     - {price['amount']} {price['currency'].upper()}{recurring_info} (ID: {price['id']})")
            else:
                print("   Prices: None")
            
            print()  # Empty line between products
    
    except Exception as e:
        print(f"Error displaying product summary: {str(e)}")


async def main():
    """Main function with examples of retrieving and displaying product information."""
    print("=== Stripe Products Retrieval Example ===")
    print(f"API Version: {stripe.api_version}")
    print(f"API Key (first 4 chars): {stripe.api_key[:4]}...")
    
    # Example 1: List all active products
    print("\n=== Example 1: List All Active Products ===")
    products = await list_all_products(limit=10)
    print(f"Found {len(products)} active products:")
    for product in products:
        print(f"- {product['name']} (ID: {product['id']})")
    
    # If we have products, show more detailed examples
    if products:
        first_product_id = products[0]['id']
        
        # Example 2: Get specific product by ID
        print(f"\n=== Example 2: Get Product by ID ({first_product_id}) ===")
        product = await get_product_by_id(first_product_id)
        if product:
            print(f"Product details:")
            print(f"- ID: {product['id']}")
            print(f"- Name: {product['name']}")
            print(f"- Description: {product.get('description', 'N/A')}")
            print(f"- Active: {product['active']}")
            print(f"- Created: {product['created']}")
        
        # Example 3: Get prices for a product
        print(f"\n=== Example 3: Get Prices for Product ({first_product_id}) ===")
        prices = await get_product_prices(first_product_id)
        print(f"Found {len(prices)} prices for product {first_product_id}:")
        for price in prices:
            recurring_info = ""
            if price['recurring']:
                recurring_info = f" ({price['recurring_interval']} recurring)"
            print(f"- {price['amount']} {price['currency'].upper()}{recurring_info} (ID: {price['id']})")
        
        # Example 4: Search products by name
        print("\n=== Example 4: Search Products by Name ===")
        search_term = products[0]['name'].split()[0] if ' ' in products[0]['name'] else products[0]['name'][:4]
        print(f"Searching for products with name containing '{search_term}'...")
        search_results = await search_products_by_name(search_term)
        print(f"Found {len(search_results)} matching products:")
        for product in search_results:
            print(f"- {product['name']} (ID: {product['id']})")
    
    # Example 5: Display detailed product summary
    print("\n=== Example 5: Display Detailed Product Summary ===")
    await display_product_summary()


if __name__ == "__main__":
    asyncio.run(main())