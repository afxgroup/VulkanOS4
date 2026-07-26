#!/usr/bin/env python3
"""Generate one-instruction probe .s files. Name encodes the area."""
import os
D = "/s/probe"
os.makedirs(D, exist_ok=True)

P = {
 # ---- scalar memory: offset units / field width ----
 "smem_load_dword_off0":      "s_load_dword s8, s[0:1], 0x0",
 "smem_load_dword_off4":      "s_load_dword s8, s[0:1], 0x4",
 "smem_load_dword_off20":     "s_load_dword s8, s[0:1], 0x20",
 "smem_load_dword_off_ff":    "s_load_dword s8, s[0:1], 0xff",
 "smem_load_dword_off_100":   "s_load_dword s8, s[0:1], 0x100",
 "smem_load_dword_off_3fc":   "s_load_dword s8, s[0:1], 0x3fc",
 "smem_load_dword_off_400":   "s_load_dword s8, s[0:1], 0x400",
 "smem_load_dword_off_ffff":  "s_load_dword s8, s[0:1], 0xffff",
 "smem_load_dword_off_fffff": "s_load_dword s8, s[0:1], 0xfffff",
 "smem_load_dword_off_unalign":"s_load_dword s8, s[0:1], 0x1",
 "smem_load_dword_soff_sgpr": "s_load_dword s8, s[0:1], s4",
 "smem_load_dword_imm_plus_sgpr": "s_load_dword s8, s[0:1], s4 offset:0x10",
 "smem_load_dwordx4":         "s_load_dwordx4 s[8:11], s[0:1], 0x0",
 "smem_load_dwordx8":         "s_load_dwordx8 s[8:15], s[0:1], 0x0",
 "smem_load_dwordx16":        "s_load_dwordx16 s[8:23], s[0:1], 0x0",
 "smem_buffer_load_dword":    "s_buffer_load_dword s8, s[0:3], 0x0",
 "smem_buffer_load_dwordx4":  "s_buffer_load_dwordx4 s[8:11], s[0:3], 0x20",
 "smem_buffer_load_dwordx8":  "s_buffer_load_dwordx8 s[8:15], s[0:3], 0x30",
 "smem_buffer_load_dwordx16": "s_buffer_load_dwordx16 s[8:23], s[0:3], 0x0",
 "smem_load_glc":             "s_load_dword s8, s[0:1], 0x0 glc",
 "smem_store_dword":          "s_store_dword s8, s[0:1], 0x0",
 "smem_dcache_inv":           "s_dcache_inv",

 # ---- vector / buffer memory ----
 "mubuf_load_dword_idxen":    "buffer_load_dword v1, v0, s[0:3], 0 idxen",
 "mubuf_load_dwordx4_idxen":  "buffer_load_dwordx4 v[1:4], v0, s[0:3], 0 idxen",
 "mubuf_load_dword_offen":    "buffer_load_dword v1, v0, s[0:3], 0 offen",
 "mubuf_load_dword_off16":    "buffer_load_dword v1, v0, s[0:3], 0 idxen offset:16",
 "mubuf_load_dword_off4095":  "buffer_load_dword v1, v0, s[0:3], 0 idxen offset:4095",
 "mubuf_load_dword_off4096":  "buffer_load_dword v1, v0, s[0:3], 0 idxen offset:4096",
 "mubuf_load_dword_soff_sgpr":"buffer_load_dword v1, v0, s[0:3], s4 idxen",
 "mubuf_load_format_xyzw":    "buffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen",
 "mubuf_load_ushort":         "buffer_load_ushort v1, v0, s[0:3], 0 idxen",
 "mubuf_load_dword_glc_slc":  "buffer_load_dword v1, v0, s[0:3], 0 idxen glc slc",
 "mubuf_store_dword":         "buffer_store_dword v1, v0, s[0:3], 0 idxen",
 "mubuf_load_dword_lds":      "buffer_load_dword v0, s[0:3], 0 idxen lds",
 "tbuffer_load_xyzw_gfx8":    "tbuffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen format:[BUF_DATA_FORMAT_32_32_32_32,BUF_NUM_FORMAT_FLOAT]",
 "tbuffer_load_xyzw_dfmtnfmt":"tbuffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen dfmt:14 nfmt:7",

 # ---- images ----
 "mimg_sample":               "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf",
 "mimg_sample_d1":            "image_sample v0, v[2:3], s[0:7], s[8:11] dmask:0x1",
 "mimg_sample_lz":            "image_sample_lz v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf",
 "mimg_sample_l":             "image_sample_l v[0:3], v[2:4], s[0:7], s[8:11] dmask:0xf",
 "mimg_sample_c":             "image_sample_c v[0:3], v[2:4], s[0:7], s[8:11] dmask:0xf",
 "mimg_sample_unorm":         "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf unorm",
 "mimg_load":                 "image_load v[0:3], v[2:3], s[0:7] dmask:0xf",
 "mimg_load_mip":             "image_load_mip v[0:3], v[2:4], s[0:7] dmask:0xf",
 "mimg_store":                "image_store v[0:3], v[2:3], s[0:7] dmask:0xf",
 "mimg_get_resinfo":          "image_get_resinfo v[0:3], v2, s[0:7] dmask:0xf",
 "mimg_sample_da":            "image_sample v[0:3], v[2:4], s[0:7], s[8:11] dmask:0xf da",
 "mimg_sample_d16":           "image_sample v[0:1], v[2:3], s[0:7], s[8:11] dmask:0xf d16",
 "mimg_sample_a16":           "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf a16",

 # ---- exports ----
 "exp_mrt0":                  "exp mrt0 v0, v1, v2, v3 done vm",
 "exp_mrt7":                  "exp mrt7 v0, v1, v2, v3 done vm",
 "exp_mrtz":                  "exp mrtz v0, v0, v0, v0 done vm",
 "exp_null":                  "exp null off, off, off, off done vm",
 "exp_pos0":                  "exp pos0 v0, v1, v2, v3 done",
 "exp_pos1":                  "exp pos1 v0, v1, v2, v3 done",
 "exp_pos3":                  "exp pos3 v0, v1, v2, v3 done",
 "exp_param0":                "exp param0 v0, v1, v2, v3 done",
 "exp_param31":               "exp param31 v0, v1, v2, v3 done",
 "exp_compr":                 "exp mrt0 v0, v0, v1, v1 done compr vm",
 "exp_no_done":               "exp param0 v0, v1, v2, v3",
 "exp_prim":                  "exp prim v0, off, off, off done",

 # ---- flat / global / scratch ----
 "flat_load_dword":           "flat_load_dword v0, v[2:3]",
 "flat_load_dwordx4":         "flat_load_dwordx4 v[0:3], v[2:3]",
 "flat_store_dword":          "flat_store_dword v[2:3], v0",
 "flat_load_dword_off":       "flat_load_dword v0, v[2:3] offset:16",
 "global_load_dword":         "global_load_dword v0, v[2:3], off",
 "global_load_dword_saddr":   "global_load_dword v0, v2, s[0:1]",
 "global_store_dword":        "global_store_dword v[2:3], v0, off",
 "scratch_load_dword":        "scratch_load_dword v0, v2, off",
 "scratch_load_dword_soff":   "scratch_load_dword v0, off, s4",

 # ---- VOP3 / VOP2 / SDWA / DPP ----
 "vop2_mul_f32":              "v_mul_f32 v0, v1, v2",
 "vop2_add_f32":              "v_add_f32 v0, v1, v2",
 "vop2_sub_f32":              "v_sub_f32 v0, v1, v2",
 "vop2_mac_f32":              "v_mac_f32 v0, v1, v2",
 "vop2_madmk_f32":            "v_madmk_f32 v0, v1, 0x40000000, v2",
 "vop3_mad_f32":              "v_mad_f32 v0, v1, v2, v3",
 "vop3_fma_f32":              "v_fma_f32 v0, v1, v2, v3",
 "vop3_fmac_f32":             "v_fmac_f32 v0, v1, v2",
 "vop3_cndmask_e64":          "v_cndmask_b32_e64 v1, -1.0, 4.0, vcc",
 "vop3_mul_f32_e64":          "v_mul_f32_e64 v0, v1, v2",
 "vop3_med3_f32":             "v_med3_f32 v0, v1, v2, v3",
 "vop3_lshl_add_u32":         "v_lshl_add_u32 v0, v1, 2, v2",
 "vop1_mov_b32":              "v_mov_b32 v0, v1",
 "vop1_rcp_f32":              "v_rcp_f32 v0, v1",
 "vopc_cmp_eq_u32_vcc":       "v_cmp_eq_u32 vcc, 1, v0",
 "vopc_cmp_eq_u32_e64":       "v_cmp_eq_u32_e64 s[0:1], 1, v0",
 "sdwa_mul_f32":              "v_mul_f32_sdwa v0, v1, v2 dst_sel:DWORD dst_unused:UNUSED_PAD src0_sel:WORD_0 src1_sel:DWORD",
 "dpp_mov_b32":               "v_mov_b32_dpp v0, v1 quad_perm:[1,0,3,2] row_mask:0xf bank_mask:0xf",
 "dpp_add_f32":               "v_add_f32_dpp v0, v1, v2 quad_perm:[0,1,2,3] row_mask:0xf bank_mask:0xf",

 # ---- 16-bit ----
 "f16_add":                   "v_add_f16 v0, v1, v2",
 "f16_mul":                   "v_mul_f16 v0, v1, v2",
 "f16_mad":                   "v_mad_f16 v0, v1, v2, v3",
 "f16_fma":                   "v_fma_f16 v0, v1, v2, v3",
 "f16_cvt_f16_f32":           "v_cvt_f16_f32 v0, v1",
 "f16_cvt_pkrtz":             "v_cvt_pkrtz_f16_f32 v0, v1, v2",
 "f16_pk_add_f16":            "v_pk_add_f16 v0, v1, v2",
 "f16_pk_mul_f16":            "v_pk_mul_f16 v0, v1, v2",
 "f16_hi_operand":            "v_add_f16 v0, v1, v2 op_sel:[1,0,0]",

 # ---- s_waitcnt field widths ----
 "wait_vmcnt0":               "s_waitcnt vmcnt(0)",
 "wait_vmcnt15":              "s_waitcnt vmcnt(15)",
 "wait_vmcnt16":              "s_waitcnt vmcnt(16)",
 "wait_vmcnt63":              "s_waitcnt vmcnt(63)",
 "wait_vmcnt64":              "s_waitcnt vmcnt(64)",
 "wait_lgkmcnt0":             "s_waitcnt lgkmcnt(0)",
 "wait_lgkmcnt15":            "s_waitcnt lgkmcnt(15)",
 "wait_lgkmcnt16":            "s_waitcnt lgkmcnt(16)",
 "wait_expcnt0":              "s_waitcnt expcnt(0)",
 "wait_all0":                 "s_waitcnt vmcnt(0) expcnt(0) lgkmcnt(0)",
 "wait_0":                    "s_waitcnt 0",

 # ---- interpolation / misc PS ----
 "interp_p1":                 "v_interp_p1_f32 v2, v0, attr0.x",
 "interp_p2":                 "v_interp_p2_f32 v2, v1, attr0.x",
 "interp_mov":                "v_interp_mov_f32 v2, p0, attr0.x",
 "interp_p1_f16":             "v_interp_p1ll_f16 v2, v0, attr0.x",
 "misc_mov_m0":               "s_mov_b32 m0, s12",
 "misc_endpgm":               "s_endpgm",
 "misc_setreg":               "s_setreg_imm32_b32 hwreg(HW_REG_MODE, 0, 2), 3",
 "misc_s_mul_i32":            "s_mul_i32 s0, s1, s2",
 "misc_s_mulk":               "s_mulk_i32 s0, 0x10",
 "misc_s_memtime":            "s_memtime s[0:1]",
 "misc_s_memrealtime":        "s_memrealtime s[0:1]",
}
for k, v in P.items():
    with open(os.path.join(D, k + ".s"), "w") as f:
        f.write(".text\n    " + v + "\n")
print(len(P), "probes written")
