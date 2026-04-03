import pandas as pd
import logging

logger = logging.getLogger(__name__)

def calculate_ema_derivatives(df: pd.DataFrame, current_price: float) -> dict:
    """
    计算港股均线衍生指标与多周期共振量化标签 (EMA MTF & V-Reversal Spec)
    结合盘中实时价格，消除指标滞后性。
    
    参数:
        df: pd.DataFrame, 必须包含 'close' 列，且按时间升序排列（历史日K线数据）
        current_price: float, 盘中实时价格
        
    返回:
        dict: 包含 'tag', 'v5', 'a5', 'bias20' 等计算结果的字典
    """
    if df is None or df.empty or 'close' not in df.columns or len(df) < 20:
        logger.warning("Data too short or missing 'close' column for EMA derivatives calculation.")
        return {"tag": "数据不足", "v5": 0.0, "a5": 0.0, "bias20": 0.0}

    # 0. 拼接或更新最新价格
    # 强制将最后一行（如果代表今天）或新增一行作为实时数据，以确保最新价格权重最大
    # 为了简化且不依赖具体日期列格式，直接用 current_price 更新或追加到最后
    # 假设 df 已经是处理好的历史K线，如果最后一条不是当前价格，我们将其追加或覆盖
    # 为保证安全，如果最后一行与当前价格差别极大（不是同一天），通常我们直接追加
    # 这里采用统一的简单策略：始终将 current_price 作为最新收盘价拼接到最后计算
    df_calc = df.copy()
    df_calc.loc[len(df_calc)] = {'close': current_price} # 增加一行代表当下

    # 1. 计算机构级 EMA
    df_calc['EMA5'] = df_calc['close'].ewm(span=5, adjust=False).mean()
    df_calc['EMA20'] = df_calc['close'].ewm(span=20, adjust=False).mean()

    # 2. 计算一阶导数 V (百分比变化率)
    df_calc['V5'] = df_calc['EMA5'].pct_change() * 100
    df_calc['V20'] = df_calc['EMA20'].pct_change() * 100

    # 3. 计算二阶导数 A (速度的差分)
    df_calc['A5'] = df_calc['V5'].diff()

    # 4. 计算实时 Bias 乖离率
    df_calc['Bias20'] = (df_calc['close'] - df_calc['EMA20']) / df_calc['EMA20'] * 100

    # 获取最后一行数据（最新盘中状态）
    latest = df_calc.iloc[-1]
    
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
        
    # 若未触发左侧信号，再进行 3.2 节的右侧共振判定及 3.3 节的拐点判定
    elif v20 > 0 and v5 > 0 and a5 > 0:
        tag = "【主升浪加速：长短共振】"
    elif v20 > 0 and v5 > 0 and a5 < 0:
        tag = "【主升浪降速：高位震荡/诱多】"
    elif v20 < 0 and v5 < 0 and a5 < 0:
        tag = "【主跌浪加速：空头长短共振】"
    elif v20 < 0 and v5 < 0 and a5 > 0:
        tag = "【跌势放缓：左侧建仓观察区】"
    elif v20 < 0 and v5 > 0:
        tag = "【短期趋势转多：均线金叉预备】"
    elif v20 > 0 and v5 < 0:
        tag = "【短期趋势转空：均线死叉预备】"
        
    return {
        "tag": tag,
        "v5": round(v5, 2) if not pd.isna(v5) else 0.0,
        "v20": round(v20, 2) if not pd.isna(v20) else 0.0,
        "a5": round(a5, 2) if not pd.isna(a5) else 0.0,
        "bias20": round(bias20, 2) if not pd.isna(bias20) else 0.0
    }
