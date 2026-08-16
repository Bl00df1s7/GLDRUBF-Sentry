"""
Strategy configuration parameters.
"""

# Timeframe
TIMEFRAME = "4H"

# Entry - Donchian Channel
DONCHIAN_LEN = 20

# Volatility - ATR
ATR_LEN = 14

# Risk Management
SL_ATR = 3.0          # Stop Loss in ATR units
TP_PCT = 0.07         # Take Profit as percentage (7%)
BE_PCT = 0.02         # Break-Even trigger as percentage (2%)

# Parabolic SAR
SAR_START = 0.03
SAR_INC = 0.02
SAR_MAX = 0.20

# Target instrument
TARGET_TICKER = "GLDRUBF"
