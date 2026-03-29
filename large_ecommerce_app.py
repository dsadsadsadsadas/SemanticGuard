"""
Large E-Commerce Application
A comprehensive e-commerce platform with multiple modules
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(Enum):
    """Payment method enumeration"""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    BANK_TRANSFER = "bank_transfer"


@dataclass
class Address:
    """Customer address data structure"""
    street: str
    city: str
    state: str
    zip_code: str
    country: str
    
    def validate(self) -> bool:
        """Validate address fields"""
        return all([
            self.street,
            self.city,
            self.state,
            self.zip_code,
            self.country
        ])
    
    def format_shipping_label(self) -> str:
        """Format address for shipping label"""
        return f"{self.street}\n{self.city}, {self.state} {self.zip_code}\n{self.country}"


@dataclass
class Customer:
    """Customer data structure"""
    customer_id: str
    email: str
    first_name: str
    last_name: str
    phone: str
    addresses: List[Address]
    created_at: datetime
    loyalty_points: int = 0
    
    def get_full_name(self) -> str:
        """Get customer's full name"""
        return f"{self.first_name} {self.last_name}"
    
    def add_loyalty_points(self, points: int) -> None:
        """Add loyalty points to customer account"""
        self.loyalty_points += points
        logger.info(f"Added {points} loyalty points to customer {self.customer_id}")
    
    def redeem_loyalty_points(self, points: int) -> bool:
        """Redeem loyalty points"""
        if self.loyalty_points >= points:
            self.loyalty_points -= points
            logger.info(f"Redeemed {points} loyalty points for customer {self.customer_id}")
            return True
        return False


@dataclass
class Product:
    """Product data structure"""
    product_id: str
    name: str
    description: str
    price: float
    category: str
    stock_quantity: int
    sku: str
    weight: float
    dimensions: Dict[str, float]
    images: List[str]
    tags: List[str]
    
    def is_in_stock(self) -> bool:
        """Check if product is in stock"""
        return self.stock_quantity > 0
    
    def update_stock(self, quantity: int) -> bool:
        """Update stock quantity"""
        if self.stock_quantity + quantity >= 0:
            self.stock_quantity += quantity
            logger.info(f"Updated stock for {self.product_id}: {self.stock_quantity}")
            return True
        return False
    
    def calculate_shipping_cost(self, destination: Address) -> float:
        """Calculate shipping cost based on weight and destination"""
        base_rate = 5.99
        weight_rate = self.weight * 0.5
        
        # International shipping
        if destination.country != "USA":
            return base_rate + weight_rate + 15.00
        
        return base_rate + weight_rate


@dataclass
class OrderItem:
    """Order item data structure"""
    product: Product
    quantity: int
    price_at_purchase: float
    
    def get_subtotal(self) -> float:
        """Calculate subtotal for this item"""
        return self.price_at_purchase * self.quantity


@dataclass
class Order:
    """Order data structure"""
    order_id: str
    customer: Customer
    items: List[OrderItem]
    shipping_address: Address
    billing_address: Address
    status: OrderStatus
    payment_method: PaymentMethod
    created_at: datetime
    updated_at: datetime
    tracking_number: Optional[str] = None
    
    def calculate_subtotal(self) -> float:
        """Calculate order subtotal"""
        return sum(item.get_subtotal() for item in self.items)
    
    def calculate_tax(self) -> float:
        """Calculate tax based on shipping address"""
        subtotal = self.calculate_subtotal()
        tax_rate = 0.08  # 8% tax rate
        return subtotal * tax_rate
    
    def calculate_shipping(self) -> float:
        """Calculate total shipping cost"""
        return sum(
            item.product.calculate_shipping_cost(self.shipping_address) 
            for item in self.items
        )
    
    def calculate_total(self) -> float:
        """Calculate order total"""
        return self.calculate_subtotal() + self.calculate_tax() + self.calculate_shipping()
    
    def update_status(self, new_status: OrderStatus) -> None:
        """Update order status"""
        self.status = new_status
        self.updated_at = datetime.now()
        logger.info(f"Order {self.order_id} status updated to {new_status.value}")


class InventoryManager:
    """Manage product inventory"""
    
    def __init__(self):
        self.products: Dict[str, Product] = {}
        self.low_stock_threshold = 10
    
    def add_product(self, product: Product) -> None:
        """Add product to inventory"""
        self.products[product.product_id] = product
        logger.info(f"Added product {product.product_id} to inventory")
    
    def remove_product(self, product_id: str) -> bool:
        """Remove product from inventory"""
        if product_id in self.products:
            del self.products[product_id]
            logger.info(f"Removed product {product_id} from inventory")
            return True
        return False
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get product by ID"""
        return self.products.get(product_id)
    
    def check_low_stock(self) -> List[Product]:
        """Get list of low stock products"""
        return [
            product for product in self.products.values()
            if product.stock_quantity <= self.low_stock_threshold
        ]
    
    def search_products(self, query: str) -> List[Product]:
        """Search products by name or description"""
        query_lower = query.lower()
        return [
            product for product in self.products.values()
            if query_lower in product.name.lower() or 
               query_lower in product.description.lower()
        ]
    
    def get_products_by_category(self, category: str) -> List[Product]:
        """Get all products in a category"""
        return [
            product for product in self.products.values()
            if product.category == category
        ]


class ShoppingCart:
    """Shopping cart management"""
    
    def __init__(self, customer: Customer):
        self.customer = customer
        self.items: Dict[str, Tuple[Product, int]] = {}
    
    def add_item(self, product: Product, quantity: int = 1) -> bool:
        """Add item to cart"""
        if not product.is_in_stock():
            logger.warning(f"Product {product.product_id} is out of stock")
            return False
        
        if product.product_id in self.items:
            current_product, current_qty = self.items[product.product_id]
            self.items[product.product_id] = (current_product, current_qty + quantity)
        else:
            self.items[product.product_id] = (product, quantity)
        
        logger.info(f"Added {quantity} of {product.product_id} to cart")
        return True
    
    def remove_item(self, product_id: str) -> bool:
        """Remove item from cart"""
        if product_id in self.items:
            del self.items[product_id]
            logger.info(f"Removed {product_id} from cart")
            return True
        return False
    
    def update_quantity(self, product_id: str, quantity: int) -> bool:
        """Update item quantity"""
        if product_id in self.items and quantity > 0:
            product, _ = self.items[product_id]
            self.items[product_id] = (product, quantity)
            logger.info(f"Updated {product_id} quantity to {quantity}")
            return True
        return False
    
    def get_total(self) -> float:
        """Calculate cart total"""
        return sum(product.price * qty for product, qty in self.items.values())
    
    def clear(self) -> None:
        """Clear all items from cart"""
        self.items.clear()
        logger.info(f"Cleared cart for customer {self.customer.customer_id}")


class PaymentProcessor:
    """Process payments"""
    
    def __init__(self):
        self.transaction_log: List[Dict] = []
    
    def process_credit_card(self, card_number: str, cvv: str, expiry: str, amount: float) -> Dict:
        """Process credit card payment"""
        # Hash sensitive data
        card_hash = hashlib.sha256(card_number.encode()).hexdigest()
        
        transaction = {
            "transaction_id": self._generate_transaction_id(),
            "card_hash": card_hash,
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        # Simulate payment processing
        if self._validate_card(card_number, cvv, expiry):
            transaction["status"] = "approved"
            logger.info(f"Credit card payment approved: {transaction['transaction_id']}")
        else:
            transaction["status"] = "declined"
            logger.warning(f"Credit card payment declined: {transaction['transaction_id']}")
        
        self.transaction_log.append(transaction)
        return transaction
    
    def process_paypal(self, email: str, amount: float) -> Dict:
        """Process PayPal payment"""
        transaction = {
            "transaction_id": self._generate_transaction_id(),
            "email": email,
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
            "status": "approved"
        }
        
        self.transaction_log.append(transaction)
        logger.info(f"PayPal payment processed: {transaction['transaction_id']}")
        return transaction
    
    def process_stripe(self, token: str, amount: float) -> Dict:
        """Process Stripe payment"""
        transaction = {
            "transaction_id": self._generate_transaction_id(),
            "stripe_token": token,
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
            "status": "approved"
        }
        
        self.transaction_log.append(transaction)
        logger.info(f"Stripe payment processed: {transaction['transaction_id']}")
        return transaction
    
    def _generate_transaction_id(self) -> str:
        """Generate unique transaction ID"""
        timestamp = datetime.now().timestamp()
        return f"TXN-{int(timestamp * 1000)}"
    
    def _validate_card(self, card_number: str, cvv: str, expiry: str) -> bool:
        """Validate credit card details"""
        # Basic validation
        if len(card_number) not in [15, 16]:
            return False
        if len(cvv) not in [3, 4]:
            return False
        return True
    
    def refund_transaction(self, transaction_id: str) -> bool:
        """Process refund for a transaction"""
        for transaction in self.transaction_log:
            if transaction["transaction_id"] == transaction_id:
                transaction["status"] = "refunded"
                logger.info(f"Refunded transaction: {transaction_id}")
                return True
        return False


class EmailService:
    """Send email notifications"""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.example.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.from_email = os.getenv("FROM_EMAIL", "noreply@ecommerce.com")
    
    def send_order_confirmation(self, order: Order) -> bool:
        """Send order confirmation email"""
        subject = f"Order Confirmation - {order.order_id}"
        body = self._format_order_email(order)
        
        return self._send_email(order.customer.email, subject, body)
    
    def send_shipping_notification(self, order: Order) -> bool:
        """Send shipping notification email"""
        subject = f"Your order has shipped - {order.order_id}"
        body = f"""
        Dear {order.customer.get_full_name()},
        
        Your order {order.order_id} has been shipped!
        Tracking Number: {order.tracking_number}
        
        Thank you for your purchase!
        """
        
        return self._send_email(order.customer.email, subject, body)
    
    def send_delivery_confirmation(self, order: Order) -> bool:
        """Send delivery confirmation email"""
        subject = f"Order Delivered - {order.order_id}"
        body = f"""
        Dear {order.customer.get_full_name()},
        
        Your order {order.order_id} has been delivered!
        
        We hope you enjoy your purchase!
        """
        
        return self._send_email(order.customer.email, subject, body)
    
    def _format_order_email(self, order: Order) -> str:
        """Format order confirmation email"""
        items_text = "\n".join([
            f"- {item.product.name} x{item.quantity}: ${item.get_subtotal():.2f}"
            for item in order.items
        ])
        
        return f"""
        Dear {order.customer.get_full_name()},
        
        Thank you for your order!
        
        Order ID: {order.order_id}
        Order Date: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}
        
        Items:
        {items_text}
        
        Subtotal: ${order.calculate_subtotal():.2f}
        Tax: ${order.calculate_tax():.2f}
        Shipping: ${order.calculate_shipping():.2f}
        Total: ${order.calculate_total():.2f}
        
        Shipping Address:
        {order.shipping_address.format_shipping_label()}
        
        Thank you for shopping with us!
        """
    
    def _send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email via SMTP"""
        try:
            # Simulate email sending
            logger.info(f"Sending email to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class AnalyticsService:
    """Track analytics and metrics"""
    
    def __init__(self):
        self.events: List[Dict] = []
        # VULNERABILITY: Hardcoded API key for analytics service
        self.analytics_api_key = "sk_live_51MZqRpL8H9vK2xJ3nF4wQ7yT6mP1sR8dC5bN9hG3fV2kX7jW4tY6uI8oP0lM3nB2vC4xZ5aS7dF9gH1jK3lQ4wE6rT8yU0iO2pA4sD6fG8hJ0kL2zX4cV6bN8mQ1wE3rT5yU7iO9pA1sD3fG5hJ7kL9zX1cV3bN5mQ7wE9rT1yU3iO5pA7sD9fG1hJ3kL5zX7cV9bN1mQ3wE5rT7yU9iO1pA3sD5fG7hJ9kL1zX3cV5bN7mQ9wE1rT3yU5iO7pA9sD1fG3hJ5kL7zX9cV1bN3mQ5wE7rT9yU1iO3pA5sD7fG9hJ1kL3zX5cV7bN9mQ1wE3rT5yU7iO9pA1sD3fG5hJ7kL9zX1cV3bN5m"
    
    def track_page_view(self, customer_id: str, page: str) -> None:
        """Track page view event"""
        event = {
            "event_type": "page_view",
            "customer_id": customer_id,
            "page": page,
            "timestamp": datetime.now().isoformat()
        }
        self.events.append(event)
        logger.debug(f"Tracked page view: {page}")
    
    def track_product_view(self, customer_id: str, product_id: str) -> None:
        """Track product view event"""
        event = {
            "event_type": "product_view",
            "customer_id": customer_id,
            "product_id": product_id,
            "timestamp": datetime.now().isoformat()
        }
        self.events.append(event)
        logger.debug(f"Tracked product view: {product_id}")
    
    def track_add_to_cart(self, customer_id: str, product_id: str, quantity: int) -> None:
        """Track add to cart event"""
        event = {
            "event_type": "add_to_cart",
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "timestamp": datetime.now().isoformat()
        }
        self.events.append(event)
        logger.debug(f"Tracked add to cart: {product_id}")
    
    def track_purchase(self, order: Order) -> None:
        """Track purchase event"""
        event = {
            "event_type": "purchase",
            "customer_id": order.customer.customer_id,
            "order_id": order.order_id,
            "total": order.calculate_total(),
            "items_count": len(order.items),
            "timestamp": datetime.now().isoformat()
        }
        self.events.append(event)
        logger.info(f"Tracked purchase: {order.order_id}")
    
    def get_customer_analytics(self, customer_id: str) -> Dict:
        """Get analytics for a specific customer"""
        customer_events = [e for e in self.events if e.get("customer_id") == customer_id]
        
        return {
            "total_events": len(customer_events),
            "page_views": len([e for e in customer_events if e["event_type"] == "page_view"]),
            "product_views": len([e for e in customer_events if e["event_type"] == "product_view"]),
            "add_to_carts": len([e for e in customer_events if e["event_type"] == "add_to_cart"]),
            "purchases": len([e for e in customer_events if e["event_type"] == "purchase"])
        }


class RecommendationEngine:
    """Product recommendation engine"""
    
    def __init__(self, inventory: InventoryManager, analytics: AnalyticsService):
        self.inventory = inventory
        self.analytics = analytics
    
    def get_recommended_products(self, customer_id: str, limit: int = 5) -> List[Product]:
        """Get recommended products for customer"""
        # Get customer's view history
        customer_events = [
            e for e in self.analytics.events 
            if e.get("customer_id") == customer_id and e["event_type"] == "product_view"
        ]
        
        if not customer_events:
            return self._get_popular_products(limit)
        
        # Get categories from viewed products
        viewed_categories = set()
        for event in customer_events:
            product = self.inventory.get_product(event["product_id"])
            if product:
                viewed_categories.add(product.category)
        
        # Recommend products from same categories
        recommendations = []
        for category in viewed_categories:
            category_products = self.inventory.get_products_by_category(category)
            recommendations.extend(category_products)
        
        return recommendations[:limit]
    
    def get_related_products(self, product_id: str, limit: int = 4) -> List[Product]:
        """Get products related to a specific product"""
        product = self.inventory.get_product(product_id)
        if not product:
            return []
        
        # Get products in same category
        related = self.inventory.get_products_by_category(product.category)
        
        # Remove the current product
        related = [p for p in related if p.product_id != product_id]
        
        return related[:limit]
    
    def _get_popular_products(self, limit: int) -> List[Product]:
        """Get most popular products based on views"""
        product_views = {}
        
        for event in self.analytics.events:
            if event["event_type"] == "product_view":
                product_id = event["product_id"]
                product_views[product_id] = product_views.get(product_id, 0) + 1
        
        # Sort by view count
        sorted_products = sorted(product_views.items(), key=lambda x: x[1], reverse=True)
        
        # Get product objects
        popular = []
        for product_id, _ in sorted_products[:limit]:
            product = self.inventory.get_product(product_id)
            if product:
                popular.append(product)
        
        return popular


class ReviewSystem:
    """Product review and rating system"""
    
    def __init__(self):
        self.reviews: Dict[str, List[Dict]] = {}
    
    def add_review(self, product_id: str, customer_id: str, rating: int, comment: str) -> bool:
        """Add a product review"""
        if rating < 1 or rating > 5:
            logger.warning("Invalid rating value")
            return False
        
        review = {
            "review_id": self._generate_review_id(),
            "customer_id": customer_id,
            "rating": rating,
            "comment": comment,
            "timestamp": datetime.now().isoformat(),
            "helpful_count": 0
        }
        
        if product_id not in self.reviews:
            self.reviews[product_id] = []
        
        self.reviews[product_id].append(review)
        logger.info(f"Added review for product {product_id}")
        return True
    
    def get_product_reviews(self, product_id: str) -> List[Dict]:
        """Get all reviews for a product"""
        return self.reviews.get(product_id, [])
    
    def get_average_rating(self, product_id: str) -> float:
        """Get average rating for a product"""
        product_reviews = self.reviews.get(product_id, [])
        
        if not product_reviews:
            return 0.0
        
        total_rating = sum(review["rating"] for review in product_reviews)
        return total_rating / len(product_reviews)
    
    def mark_review_helpful(self, product_id: str, review_id: str) -> bool:
        """Mark a review as helpful"""
        product_reviews = self.reviews.get(product_id, [])
        
        for review in product_reviews:
            if review["review_id"] == review_id:
                review["helpful_count"] += 1
                logger.debug(f"Marked review {review_id} as helpful")
                return True
        
        return False
    
    def _generate_review_id(self) -> str:
        """Generate unique review ID"""
        timestamp = datetime.now().timestamp()
        return f"REV-{int(timestamp * 1000)}"


class DiscountEngine:
    """Manage discounts and promotions"""
    
    def __init__(self):
        self.discount_codes: Dict[str, Dict] = {}
    
    def create_discount_code(self, code: str, discount_percent: float, 
                            expiry_date: datetime, max_uses: int = None) -> bool:
        """Create a new discount code"""
        if code in self.discount_codes:
            logger.warning(f"Discount code {code} already exists")
            return False
        
        self.discount_codes[code] = {
            "discount_percent": discount_percent,
            "expiry_date": expiry_date,
            "max_uses": max_uses,
            "current_uses": 0,
            "active": True
        }
        
        logger.info(f"Created discount code: {code}")
        return True
    
    def validate_discount_code(self, code: str) -> Tuple[bool, str]:
        """Validate a discount code"""
        if code not in self.discount_codes:
            return False, "Invalid discount code"
        
        discount = self.discount_codes[code]
        
        if not discount["active"]:
            return False, "Discount code is inactive"
        
        if datetime.now() > discount["expiry_date"]:
            return False, "Discount code has expired"
        
        if discount["max_uses"] and discount["current_uses"] >= discount["max_uses"]:
            return False, "Discount code has reached maximum uses"
        
        return True, "Valid discount code"
    
    def apply_discount(self, code: str, amount: float) -> Tuple[float, bool]:
        """Apply discount to an amount"""
        is_valid, message = self.validate_discount_code(code)
        
        if not is_valid:
            logger.warning(f"Failed to apply discount: {message}")
            return amount, False
        
        discount = self.discount_codes[code]
        discount_amount = amount * (discount["discount_percent"] / 100)
        final_amount = amount - discount_amount
        
        discount["current_uses"] += 1
        logger.info(f"Applied discount code {code}: ${discount_amount:.2f} off")
        
        return final_amount, True


class ECommerceApplication:
    """Main e-commerce application"""
    
    def __init__(self):
        self.inventory = InventoryManager()
        self.payment_processor = PaymentProcessor()
        self.email_service = EmailService()
        self.analytics = AnalyticsService()
        self.recommendation_engine = RecommendationEngine(self.inventory, self.analytics)
        self.review_system = ReviewSystem()
        self.discount_engine = DiscountEngine()
        self.active_carts: Dict[str, ShoppingCart] = {}
        self.orders: Dict[str, Order] = {}
        self.customers: Dict[str, Customer] = {}
    
    def register_customer(self, email: str, first_name: str, last_name: str, 
                         phone: str, address: Address) -> Customer:
        """Register a new customer"""
        customer_id = self._generate_customer_id()
        customer = Customer(
            customer_id=customer_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            addresses=[address],
            created_at=datetime.now()
        )
        
        self.customers[customer_id] = customer
        logger.info(f"Registered new customer: {customer_id}")
        return customer
    
    def create_order(self, customer_id: str, cart: ShoppingCart, 
                    shipping_address: Address, billing_address: Address,
                    payment_method: PaymentMethod) -> Optional[Order]:
        """Create a new order from shopping cart"""
        customer = self.customers.get(customer_id)
        if not customer:
            logger.error(f"Customer {customer_id} not found")
            return None
        
        if not cart.items:
            logger.warning("Cannot create order from empty cart")
            return None
        
        # Create order items
        order_items = []
        for product, quantity in cart.items.values():
            order_item = OrderItem(
                product=product,
                quantity=quantity,
                price_at_purchase=product.price
            )
            order_items.append(order_item)
            
            # Update inventory
            product.update_stock(-quantity)
        
        # Create order
        order_id = self._generate_order_id()
        order = Order(
            order_id=order_id,
            customer=customer,
            items=order_items,
            shipping_address=shipping_address,
            billing_address=billing_address,
            status=OrderStatus.PENDING,
            payment_method=payment_method,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.orders[order_id] = order
        
        # Clear cart
        cart.clear()
        
        # Track analytics
        self.analytics.track_purchase(order)
        
        # Send confirmation email
        self.email_service.send_order_confirmation(order)
        
        # Award loyalty points
        points = int(order.calculate_total())
        customer.add_loyalty_points(points)
        
        logger.info(f"Created order: {order_id}")
        return order
    
    def _generate_customer_id(self) -> str:
        """Generate unique customer ID"""
        timestamp = datetime.now().timestamp()
        return f"CUST-{int(timestamp * 1000)}"
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        timestamp = datetime.now().timestamp()
        return f"ORD-{int(timestamp * 1000)}"


# Example usage and initialization
if __name__ == "__main__":
    # Initialize application
    app = ECommerceApplication()
    
    # Add sample products
    sample_products = [
        Product(
            product_id="PROD-001",
            name="Wireless Headphones",
            description="High-quality wireless headphones with noise cancellation",
            price=199.99,
            category="Electronics",
            stock_quantity=50,
            sku="WH-001",
            weight=0.5,
            dimensions={"length": 8, "width": 7, "height": 3},
            images=["headphones1.jpg", "headphones2.jpg"],
            tags=["audio", "wireless", "electronics"]
        ),
        Product(
            product_id="PROD-002",
            name="Smart Watch",
            description="Fitness tracking smart watch with heart rate monitor",
            price=299.99,
            category="Electronics",
            stock_quantity=30,
            sku="SW-001",
            weight=0.2,
            dimensions={"length": 2, "width": 2, "height": 0.5},
            images=["watch1.jpg", "watch2.jpg"],
            tags=["wearable", "fitness", "electronics"]
        )
    ]
    
    for product in sample_products:
        app.inventory.add_product(product)
    
    logger.info("E-Commerce application initialized successfully")
