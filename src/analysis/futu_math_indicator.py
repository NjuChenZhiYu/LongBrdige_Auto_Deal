import pandas as pd
import logging

logger = logging.getLogger(__name__)

def calculate_ema_derivatives(df: pd.DataFrame) -> dict:
    """
    计算港股均线衍生指标与多周期共振量化标签 (EMA MTF & V-Reversal Spec)
    
    参数:
        df: pd.DataFrame, 必须包含 'close' 列，且按时间升序排列（最新的在最后）
        
    返回:
        dict: 包含 'tag', 'v5', 'a5', 'bias20' 等计算结果的字典
    """
    if df is None or df.empty or 'close' not in df.columns or len(df) < 20:
        logger.warning("Data too short or missing 'close' column for EMA derivatives calculation.")
        return {"tag": "数据不足", "v5": 0.0, "a5": 0.0, "bias20": 0.0}

    # 1. 计算机构级 EMA
    df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()

    # 2. 计算一阶导数 V (百分比变化率)
    df['V5'] = df['EMA5'].pct_change() * 100
    df['V20'] = df['EMA20'].pct_change() * 100

    # 3. 计算二阶导数 A (速度的差分)
    df['A5'] = df['V5'].diff()

    # 4. 计算 Bias 乖离率
    df['Bias20'] = (df['close'] - df['EMA20']) / df['EMA20'] * 100

    # 获取最后一行数据（最新状态）
    latest = df.iloc[-1]
    
    v5 = latest['V5']
    v20 = latest['V20']
    a5 = latest['A5']
    bias20 = latest['Bias20']
    
    tag = "【震荡市：方向不明】"

    # 优先判断 3.1 节的 Bias 极限值场景 (左侧中和策略)
    if bias20 <= -12.0 and a5 > 0:
        tag = "【极度超跌：V型反转预备】"
    elif bias20 >= 12.0 and a5 < 0:
        tag = "【极度超买：估值透支预警】"
    # 若未触发左侧信号，再进行 3.2 节的右侧共振判定
    elif v20 > 0 and v5 > 0 and a5 > 0:
        tag = "【主升浪加速：长短共振】"
    elif v20 > 0 and v5 > 0 and a5 < 0:
        tag = "【顶部诱多：动能背离】"
    elif v20 < 0 and v5 < 0:
        tag = "【主跌浪向下：空头排列】"
        
    return {
        "tag": tag,
        "v5": round(v5, 2) if not pd.isna(v5) else 0.0,
        "v20": round(v20, 2) if not pd.isna(v20) else 0.0,
        "a5": round(a5, 2) if not pd.isna(a5) else 0.0,
        "bias20": round(bias20, 2) if not pd.isna(bias20) else 0.0
    }
