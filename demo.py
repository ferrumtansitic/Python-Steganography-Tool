import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import numpy as np
import math
import os

class LSBSystem:
    """
    LSB核心逻辑类：负责图像的位操作
    """
    def __init__(self):
        self.header_len = 32  # 使用前32位(4字节)存储消息长度

    def text_to_bits(self, text):
        """将文本转换为二进制字符串"""
        bits = bin(int.from_bytes(text.encode('utf-8'), 'big'))[2:]
        return bits.zfill(8 * ((len(bits) + 7) // 8))

    def bits_to_text(self, bits):
        """将二进制字符串转换回文本"""
        try:
            n = int(bits, 2)
            return n.to_bytes((n.bit_length() + 7) // 8, 'big').decode('utf-8', errors='ignore')
        except:
            return "[解码错误]"

    def encode(self, image_path, secret_text, output_path):
        """
        核心功能：嵌入信息
        原理：将文本二进制长度作为头文件 + 文本二进制内容，写入像素LSB
        """
        img = Image.open(image_path).convert('RGB')
        width, height = img.size
        array = np.array(img)
        
        # 1. 准备数据：长度头 + 实际数据
        text_bits = self.text_to_bits(secret_text)
        length_bits = bin(len(text_bits))[2:].zfill(self.header_len) # 32位长度头
        full_bits = length_bits + text_bits
        
        total_pixels = width * height
        max_capacity = total_pixels * 3 # RGB三个通道都可以存
        
        if len(full_bits) > max_capacity:
            raise ValueError(f"信息过长！图片最多容纳 {max_capacity} bit，当前需要 {len(full_bits)} bit")

        # 2. 嵌入过程 (使用numpy加速)
        flat_array = array.reshape(-1) # 展平为一维数组
        
        # 将二进制字符串转换为整数列表
        bit_list = np.array([int(b) for b in full_bits], dtype=np.uint8)
        
        # 利用位运算替换LSB： 先 & 254 (清零最后一位)，再 | bit (写入新位)
        # 只修改前 N 个像素值，N = len(full_bits)
        flat_array[:len(bit_list)] = (flat_array[:len(bit_list)] & 254) | bit_list
        
        # 3. 恢复形状并保存
        new_array = flat_array.reshape((height, width, 3))
        new_img = Image.fromarray(new_array)
        # 强制保存为PNG以防压缩丢失数据
        if not output_path.lower().endswith(".png"):
            output_path += ".png"
        new_img.save(output_path)
        return output_path

    def decode(self, image_path):
        """核心功能：提取信息"""
        img = Image.open(image_path).convert('RGB')
        array = np.array(img)
        flat_array = array.reshape(-1)
        
        # 1. 提取所有LSB
        lsb_bits = flat_array & 1
        
        # 2. 读取前32位获取长度
        length_bits_list = lsb_bits[:self.header_len]
        length_str = "".join(map(str, length_bits_list))
        msg_len = int(length_str, 2)
        
        # 3. 根据长度读取后续信息
        if msg_len > len(lsb_bits) - self.header_len:
            return "错误：未能检测到有效的隐写标记"
            
        msg_bits_list = lsb_bits[self.header_len : self.header_len + msg_len]
        msg_bits_str = "".join(map(str, msg_bits_list))
        
        return self.bits_to_text(msg_bits_str)

    def calculate_psnr(self, img1_path, img2_path):
        """
        核心指标：计算PSNR
        论文数据来源：越高代表图片越像，通常 > 30dB 人眼就看不出了
        """
        img1 = np.array(Image.open(img1_path).convert('RGB'), dtype=np.float64)
        img2 = np.array(Image.open(img2_path).convert('RGB'), dtype=np.float64)
        
        mse = np.mean((img1 - img2) ** 2)
        if mse == 0:
            return float('inf') # 两图完全一样
        
        return 10 * math.log10(255.0**2 / mse)


class App:
    """
    GUI界面类：负责显示
    """
    def __init__(self, root):
        self.root = root
        self.root.title("LSB图像隐写与安全传输系统 v1.0")
        self.root.geometry("700x550")
        self.lsb = LSBSystem()
        self.img_path = None
        self.stego_path = None

        self._init_ui()

    def _init_ui(self):
        # 使用Notebook实现分页
        tab_control = ttk.Notebook(self.root)
        
        self.tab1 = ttk.Frame(tab_control) # 发送端（加密）
        self.tab2 = ttk.Frame(tab_control) # 接收端（解密）
        self.tab3 = ttk.Frame(tab_control) # 质量分析（PSNR）
        
        tab_control.add(self.tab1, text=' 发送端：信息隐藏 ')
        tab_control.add(self.tab2, text=' 接收端：信息提取 ')
        tab_control.add(self.tab3, text=' 质量分析(PSNR) ')
        tab_control.pack(expand=1, fill="both")

        # --- Tab 1: 隐藏 ---
        frame1 = tk.LabelFrame(self.tab1, text="操作步骤")
        frame1.pack(fill="both", expand=True, padx=10, pady=10)
        
        tk.Button(frame1, text="1. 选择载体图片 (原图)", command=self.load_image_tab1).pack(pady=5)
        self.lbl_path1 = tk.Label(frame1, text="未选择", fg="gray")
        self.lbl_path1.pack()
        
        tk.Label(frame1, text="2. 输入要隐藏的秘密信息:").pack(pady=5)
        self.txt_input = tk.Text(frame1, height=5)
        self.txt_input.pack(padx=10, pady=5, fill="x")
        
        tk.Button(frame1, text="3. 执行隐写并保存", command=self.do_hide, bg="#dddddd").pack(pady=10)

        # --- Tab 2: 提取 ---
        frame2 = tk.LabelFrame(self.tab2, text="操作步骤")
        frame2.pack(fill="both", expand=True, padx=10, pady=10)
        
        tk.Button(frame2, text="1. 选择含密图片 (Stego Image)", command=self.load_image_tab2).pack(pady=5)
        self.lbl_path2 = tk.Label(frame2, text="未选择", fg="gray")
        self.lbl_path2.pack()
        
        tk.Button(frame2, text="2. 提取秘密信息", command=self.do_extract).pack(pady=10)
        
        tk.Label(frame2, text="解密结果:").pack(pady=5)
        self.txt_output = tk.Text(frame2, height=5)
        self.txt_output.pack(padx=10, pady=5, fill="x")

        # --- Tab 3: PSNR分析 ---
        frame3 = tk.LabelFrame(self.tab3, text="图像质量评估")
        frame3.pack(fill="both", expand=True, padx=10, pady=10)
        
        tk.Button(frame3, text="选择原图", command=self.load_psnr_orig).grid(row=0, column=0, padx=5, pady=5)
        self.lbl_psnr_orig = tk.Label(frame3, text="未选择")
        self.lbl_psnr_orig.grid(row=0, column=1)
        
        tk.Button(frame3, text="选择隐写后图片", command=self.load_psnr_stego).grid(row=1, column=0, padx=5, pady=5)
        self.lbl_psnr_stego = tk.Label(frame3, text="未选择")
        self.lbl_psnr_stego.grid(row=1, column=1)
        
        tk.Button(frame3, text="计算 PSNR 值", command=self.do_calc_psnr, bg="#dddddd").grid(row=2, column=0, columnspan=2, pady=20)
        self.lbl_result_psnr = tk.Label(frame3, text="PSNR: N/A", font=("Arial", 16, "bold"), fg="blue")
        self.lbl_result_psnr.grid(row=3, column=0, columnspan=2)
        
        tk.Label(frame3, text="说明: PSNR > 30dB 表示肉眼难以察觉差异\n本系统通常可达 50dB 以上", fg="gray").grid(row=4, column=0, columnspan=2, pady=10)

    # --- 逻辑处理 ---
    def load_image_tab1(self):
        f = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.bmp;*.jpg")])
        if f:
            self.img_path = f
            self.lbl_path1.config(text=f)

    def do_hide(self):
        if not self.img_path:
            messagebox.showerror("错误", "请先选择载体图片")
            return
        text = self.txt_input.get("1.0", "end-1c")
        if not text:
            messagebox.showerror("错误", "请输入要隐藏的文字")
            return
            
        save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png")])
        if save_path:
            try:
                final_path = self.lsb.encode(self.img_path, text, save_path)
                messagebox.showinfo("成功", f"隐写完成！\n图片已保存至: {final_path}\n请去'质量分析'页签计算PSNR。")
            except Exception as e:
                messagebox.showerror("失败", str(e))

    def load_image_tab2(self):
        f = filedialog.askopenfilename(filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")])
        if f:
            self.stego_path = f
            self.lbl_path2.config(text=f)

    def do_extract(self):
        if not self.stego_path:
            messagebox.showerror("错误", "请先选择含密图片")
            return
        try:
            msg = self.lsb.decode(self.stego_path)
            self.txt_output.delete("1.0", "end")
            self.txt_output.insert("1.0", msg)
        except Exception as e:
            messagebox.showerror("解析失败", f"无法提取信息: {str(e)}")

    def load_psnr_orig(self):
        f = filedialog.askopenfilename()
        if f: self.lbl_psnr_orig.config(text=os.path.basename(f)); self.psnr_p1 = f

    def load_psnr_stego(self):
        f = filedialog.askopenfilename()
        if f: self.lbl_psnr_stego.config(text=os.path.basename(f)); self.psnr_p2 = f

    def do_calc_psnr(self):
        try:
            val = self.lsb.calculate_psnr(self.psnr_p1, self.psnr_p2)
            self.lbl_result_psnr.config(text=f"PSNR: {val:.4f} dB")
        except:
            messagebox.showerror("错误", "请确保已选择两张图片且尺寸一致")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
