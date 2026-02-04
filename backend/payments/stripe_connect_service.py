"""
Stripe Connect Integration Service
Handles connected accounts, onboarding, and destination charges for marketplace
"""

from stripe import StripeClient
from django.conf import settings
from django.utils import timezone
from authentication.models import CustomUser

# Initialize Stripe Client
# IMPORTANT: Set STRIPE_SECRET_KEY in your environment variables
if not settings.STRIPE_SECRET_KEY:
    raise ValueError(
        "STRIPE_SECRET_KEY is not set. "
        "Please add it to your settings.py or environment variables. "
        "Get your key from: https://dashboard.stripe.com/apikeys"
    )

stripe_client = StripeClient(settings.STRIPE_SECRET_KEY)


class StripeConnectService:
    """Service for managing Stripe Connect accounts and payments"""
    
    @staticmethod
    def create_connected_account(user: CustomUser) -> dict:
        """
        Create a Stripe Connected Account for a seller using V2 API
        
        Args:
            user: CustomUser instance (seller)
            
        Returns:
            dict: Account object from Stripe
            
        The platform is responsible for:
        - Pricing (we set product prices)
        - Fee collection (we collect marketplace fees)
        - Losses (we handle chargebacks)
        """
        
        # Validate user is a seller
        if not user.is_seller:
            raise ValueError("User must be a seller to create a connected account")
        
        try:
            # Create connected account using V2 API
            # DO NOT use top-level 'type' parameter
            account = stripe_client.v2.core.accounts.create({
                # Display name shown to customers
                "display_name": user.get_full_name() or user.email,
                
                # Contact email for Stripe communications
                "contact_email": user.email,
                
                # Identity information
                "identity": {
                    "country": "BR",  # Brazil - change if needed
                },
                
                # Express dashboard - simplified interface for sellers
                "dashboard": "express",
                
                # Platform handles fees and losses
                "defaults": {
                    "responsibilities": {
                        # Platform collects all fees
                        "fees_collector": "application",
                        # Platform handles disputes/chargebacks
                        "losses_collector": "application",
                    },
                },
                
                # Configuration for receiving payments
                "configuration": {
                    "recipient": {
                        "capabilities": {
                            # Enable transfers to seller's Stripe Balance
                            "stripe_balance": {
                                "stripe_transfers": {
                                    "requested": True,
                                },
                            },
                        },
                    },
                },
            })
            
            # Store the Stripe account ID in the user model
            user.stripe_account_id = account.id
            user.save(update_fields=['stripe_account_id'])
            
            return account
            
        except Exception as e:
            raise Exception(f"Failed to create Stripe connected account: {str(e)}")
    
    @staticmethod
    def create_account_link(user: CustomUser, refresh_url: str, return_url: str) -> dict:
        """
        Create an Account Link for onboarding using V2 API
        
        Args:
            user: CustomUser instance
            refresh_url: URL to redirect if link expires
            return_url: URL to redirect after onboarding complete
            
        Returns:
            dict: Account link object with URL
            
        The account link allows sellers to:
        - Verify their identity
        - Add bank account information
        - Complete tax forms
        - Accept Stripe's terms of service
        """
        
        if not user.stripe_account_id:
            raise ValueError("User does not have a connected account")
        
        try:
            # Create account link using V2 API
            account_link = stripe_client.v2.core.account_links.create({
                # Connected account ID
                "account": user.stripe_account_id,
                
                # Onboarding use case
                "use_case": {
                    "type": "account_onboarding",
                    "account_onboarding": {
                        # Configure recipient capabilities
                        "configurations": ["recipient"],
                        
                        # Where to redirect if link expires (expires in 24h)
                        "refresh_url": refresh_url,
                        
                        # Where to redirect after completion
                        "return_url": return_url,
                    },
                },
            })
            
            return account_link
            
        except Exception as e:
            raise Exception(f"Failed to create account link: {str(e)}")
    
    @staticmethod
    def get_account_status(stripe_account_id: str) -> dict:
        """
        Get the current status of a connected account
        
        Args:
            stripe_account_id: Stripe account ID
            
        Returns:
            dict: Account status information
            
        Status includes:
        - ready_to_receive_payments: Can receive transfers
        - onboarding_complete: All requirements satisfied
        - requirements_status: currently_due, past_due, or satisfied
        """
        
        try:
            # Retrieve account with configuration and requirements
            # Include specific fields needed for status check
            account = stripe_client.v2.core.accounts.retrieve(
                stripe_account_id,
                params={
                    "include": ["configuration.recipient", "requirements"]
                }
            )
            
            # Check if account can receive payments
            # Status must be 'active' for stripe_transfers capability
            ready_to_receive_payments = (
                account.get("configuration", {})
                .get("recipient", {})
                .get("capabilities", {})
                .get("stripe_balance", {})
                .get("stripe_transfers", {})
                .get("status") == "active"
            )
            
            # Check requirements status
            requirements_summary = account.get("requirements", {}).get("summary", {})
            minimum_deadline = requirements_summary.get("minimum_deadline", {})
            requirements_status = minimum_deadline.get("status")
            
            # Onboarding is complete when no requirements are due
            onboarding_complete = (
                requirements_status not in ["currently_due", "past_due"]
            )
            
            return {
                "ready_to_receive_payments": ready_to_receive_payments,
                "onboarding_complete": onboarding_complete,
                "requirements_status": requirements_status,
                "account": account,
            }
            
        except Exception as e:
            raise Exception(f"Failed to retrieve account status: {str(e)}")
    
    @staticmethod
    def create_checkout_session_with_destination_charge(
        order,
        seller_account_id: str,
        application_fee_amount: int,
        success_url: str,
        cancel_url: str = None
    ) -> dict:
        """
        Create a Checkout Session with destination charge
        
        Args:
            order: Order instance
            seller_account_id: Stripe connected account ID
            application_fee_amount: Platform fee in cents
            success_url: URL after successful payment
            cancel_url: URL if payment is cancelled
            
        Returns:
            dict: Checkout session object
            
        Destination Charge Flow:
        1. Customer pays total amount to platform
        2. Platform keeps application_fee_amount
        3. Remaining amount transferred to seller's account
        """
        
        try:
            # Prepare line items from order
            line_items = []
            
            for item in order.items.all():
                line_items.append({
                    "price_data": {
                        "currency": "brl",  # Brazilian Real
                        "product_data": {
                            "name": item.product_name,
                            "description": f"{item.brand_name} - {item.condition_name}",
                        },
                        "unit_amount": int(float(item.unit_price) * 100),  # Convert to cents
                    },
                    "quantity": item.quantity,
                })
            
            # Add shipping as a line item if applicable
            if order.shipping_cost > 0:
                line_items.append({
                    "price_data": {
                        "currency": "brl",
                        "product_data": {
                            "name": "Frete",
                            "description": "Custo de envio",
                        },
                        "unit_amount": int(float(order.shipping_cost) * 100),
                    },
                    "quantity": 1,
                })
            
            # Create checkout session with destination charge
            session = stripe_client.checkout.sessions.create({
                # Line items to purchase
                "line_items": line_items,
                
                # Payment Intent configuration
                "payment_intent_data": {
                    # Platform fee (marketplace commission)
                    "application_fee_amount": application_fee_amount,
                    
                    # Transfer remaining to seller
                    "transfer_data": {
                        "destination": seller_account_id,
                    },
                    
                    # Store order ID in metadata
                    "metadata": {
                        "order_id": str(order.id),
                        "order_number": order.order_number,
                    },
                },
                
                # One-time payment
                "mode": "payment",
                
                # Success and cancel URLs
                "success_url": success_url,
                "cancel_url": cancel_url or success_url,
                
                # Store order metadata
                "metadata": {
                    "order_id": str(order.id),
                },
            })
            
            return session
            
        except Exception as e:
            raise Exception(f"Failed to create checkout session: {str(e)}")
    
    @staticmethod
    def handle_account_requirements_updated(event_id: str) -> dict:
        """
        Handle v2.core.account[requirements].updated webhook event
        
        This event fires when account requirements change due to:
        - Regulatory changes
        - Card network updates
        - Financial institution requirements
        
        Args:
            event_id: Stripe event ID (from thin webhook)
            
        Returns:
            dict: Event data
        """
        
        try:
            # Retrieve full event data
            # Thin events only contain event ID, must fetch full data
            event = stripe_client.v2.core.events.retrieve(event_id)
            
            # Extract account ID from event
            account_id = event.get("data", {}).get("object", {}).get("id")
            
            if not account_id:
                raise ValueError("No account ID in event data")
            
            # Find user with this Stripe account
            try:
                user = CustomUser.objects.get(stripe_account_id=account_id)
            except CustomUser.DoesNotExist:
                raise ValueError(f"No user found for account {account_id}")
            
            # Get updated account status
            status = StripeConnectService.get_account_status(account_id)
            
            # TODO: Send notification to user about requirements
            # - Email notification
            # - In-app notification
            # - SMS if critical
            
            return {
                "event": event,
                "user": user,
                "status": status,
            }
            
        except Exception as e:
            raise Exception(f"Failed to handle requirements update: {str(e)}")
    
    @staticmethod
    def handle_capability_status_updated(event_id: str) -> dict:
        """
        Handle v2.core.account[.recipient].capability_status_updated webhook
        
        Fires when capability status changes:
        - inactive -> active (can now receive payments)
        - active -> inactive (temporarily disabled)
        - pending -> active (verification complete)
        
        Args:
            event_id: Stripe event ID
            
        Returns:
            dict: Event data
        """
        
        try:
            # Retrieve full event
            event = stripe_client.v2.core.events.retrieve(event_id)
            
            # Extract account and capability info
            data = event.get("data", {}).get("object", {})
            account_id = data.get("id")
            
            # Find user
            try:
                user = CustomUser.objects.get(stripe_account_id=account_id)
            except CustomUser.DoesNotExist:
                raise ValueError(f"No user found for account {account_id}")
            
            # Get updated status
            status = StripeConnectService.get_account_status(account_id)
            
            # Update user verification status if now active
            if status["ready_to_receive_payments"]:
                user.seller_verified = True
                user.seller_verified_at = timezone.now()
                user.save(update_fields=['seller_verified', 'seller_verified_at'])
            
            return {
                "event": event,
                "user": user,
                "status": status,
            }
            
        except Exception as e:
            raise Exception(f"Failed to handle capability update: {str(e)}")
    
    @staticmethod
    def calculate_platform_fee(amount: float, fee_percentage: float = None) -> int:
        """
        Calculate platform fee in cents
        
        Args:
            amount: Order total in BRL
            fee_percentage: Fee percentage (default from settings)
            
        Returns:
            int: Fee amount in cents
        """
        
        if fee_percentage is None:
            fee_percentage = getattr(settings, 'PLATFORM_FEE_PERCENTAGE', 10)
        
        fee_amount = amount * (fee_percentage / 100)
        return int(fee_amount * 100)  # Convert to cents