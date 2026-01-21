import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
import zipfile

# 页面设置
st.set_page_config(page_title="EIS 多文件批量处理器", layout="wide")

st.title("🧪 EIS data splitter")
st.markdown("上传一个或多个 CSV 文件，手动指定行列索引，自动拆分 Sweep 轮次。")

# --- 侧边栏：交互参数配置 ---
st.sidebar.header("🛠 数据提取配置")

skip_rows = st.sidebar.number_input("数据起始行 (从0开始数, 表头所在行)", value=4, step=1)
col_freq = st.sidebar.number_input("频率所在列索引 (A=0, B=1...)", value=4, step=1)
col_rez = st.sidebar.number_input("阻抗实部 Z' 索引", value=10, step=1)
col_imz = st.sidebar.number_input("阻抗虚部 Z'' 索引", value=11, step=1)

st.sidebar.divider()
st.sidebar.info("""
**填写指南：**
1. 查看下方的【原始数据坐标参考】。
2. 找到第一个频率点出现的行号，填入‘起始行’。
3. 找到 Freq, Z', Z'' 所在的列号。
""")

# --- 主界面：文件上传 ---
uploaded_files = st.file_uploader("选择一个或多个 EIS CSV 文件", type="csv", accept_multiple_files=True)

if uploaded_files:
    # --- 辅助工具：预览第一个文件 ---
    st.subheader("🔍 原始数据坐标参考 (以第一个文件为例)")
    
    test_content = uploaded_files[0].read()
    uploaded_files[0].seek(0)
    
    # 检测编码
    try:
        test_content.decode('utf-8')
        encoding = 'utf-8'
    except:
        encoding = 'gbk'

    # 【修复核心】：使用 names 预设 100 列，避免 ParserError
    try:
        preview_df = pd.read_csv(
            io.BytesIO(test_content), 
            header=None, 
            names=range(100),  # 强制分配 100 列，解决列数不一报错
            nrows=30, 
            encoding=encoding
        )
        # 删掉全是空的列，方便显示
        preview_df = preview_df.dropna(axis=1, how='all')
        
        st.write("请根据下表的**行索引(左侧)**和**列索引(顶部数字)**填写侧边栏参数：")
        st.dataframe(preview_df)
    except Exception as e:
        st.error(f"预览加载失败: {e}")

    # --- 执行处理 ---
    if st.button("⚡ 开始批量处理所有文件"):
        all_processed_data = {}
        progress_bar = st.progress(0)

        for idx, file in enumerate(uploaded_files):
            try:
                file.seek(0)
                # 【修复核心】：读取时同样预设足够多的列名，并跳过前 skip_rows 行
                df_raw = pd.read_csv(
                    file, 
                    header=None, 
                    names=range(100), 
                    skiprows=skip_rows, 
                    encoding=encoding
                )
                
                # 提取数据并转为数值
                df_clean = pd.DataFrame()
                df_clean['Freq'] = pd.to_numeric(df_raw.iloc[:, col_freq], errors='coerce')
                df_clean['Z_real'] = pd.to_numeric(df_raw.iloc[:, col_rez], errors='coerce')
                df_clean['Z_imag'] = pd.to_numeric(df_raw.iloc[:, col_imz], errors='coerce')
                
                # 剔除无效行（空行或非数字行）
                df_clean = df_clean.dropna().reset_index(drop=True)

                if len(df_clean) > 0:
                    # 轮次识别
                    sweeps = [1]
                    f_vals = df_clean['Freq'].values
                    current_sweep = 1
                    for i in range(1, len(f_vals)):
                        # 频率突跳判定（EIS通常是从高频到低频，如果突然变大很多，就是新一轮）
                        if f_vals[i] > f_vals[i-1] * 2:
                            current_sweep += 1
                        sweeps.append(current_sweep)
                    df_clean['Sweep'] = sweeps
                    all_processed_data[file.name] = df_clean
                
            except Exception as e:
                st.warning(f"文件 {file.name} 处理跳过，原因: {e}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))

        # --- 下载区 ---
        if all_processed_data:
            st.divider()
            st.success(f"✅ 已成功处理 {len(all_processed_data)} 个文件！")

            # 绘制第一个文件的图
            first_key = list(all_processed_data.keys())[0]
            df_plot = all_processed_data[first_key]
            fig = go.Figure()
            for s in df_plot['Sweep'].unique():
                sub = df_plot[df_plot['Sweep'] == s]
                fig.add_trace(go.Scatter(x=sub['Z_real'], y=-sub['Z_imag'], mode='lines+markers', name=f'Sweep {s}'))
            fig.update_layout(title=f"预览: {first_key}", xaxis_title="Z' / Ω", yaxis_title="-Z'' / Ω", yaxis=dict(scaleanchor="x", scaleratio=1))
            st.plotly_chart(fig)

            # 打包
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for filename, data in all_processed_data.items():
                    base_name = filename.rsplit('.', 1)[0]
                    for s in data['Sweep'].unique():
                        subset = data[data['Sweep'] == s][['Freq', 'Z_real', 'Z_imag']]
                        txt_content = subset.to_csv(sep='\t', index=False, header=False)
                        zip_file.writestr(f"{base_name}/{base_name}_Sweep_{s}.txt", txt_content)

            st.download_button("🎁 下载全部处理结果 (ZIP)", zip_buffer.getvalue(), "EIS_Results.zip")

else:
    st.info("👋 请在上方上传 CSV 文件。")