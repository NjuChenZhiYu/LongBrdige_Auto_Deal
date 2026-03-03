
import math
from scipy.stats import norm

def calculate_black_scholes(S, K, T, r, sigma, option_type="call"):
    """
    Calculate Black-Scholes Delta for European option.
    
    Args:
        S (float): Spot price of underlying asset
        K (float): Strike price
        T (float): Time to expiration in years
        r (float): Risk-free interest rate (decimal, e.g., 0.05)
        sigma (float): Volatility of underlying asset (decimal, e.g., 0.20)
        option_type (str): "call" or "put"
        
    Returns:
        float: Delta value
    """
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    
    if option_type == "call":
        delta = norm.cdf(d1)
    elif option_type == "put":
        delta = norm.cdf(d1) - 1
    else:
        raise ValueError("Invalid option type. Must be 'call' or 'put'.")
        
    return delta
