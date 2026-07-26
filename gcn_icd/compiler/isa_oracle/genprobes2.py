#!/usr/bin/env python3
import os
D = "/s/probe"
for f in os.listdir(D):
    os.remove(os.path.join(D, f))
P = {
 # ---- MUBUF cache-policy / tfe bit placement ----
 "mb_plain":        "buffer_load_dword v1, v0, s[0:3], 0 idxen",
 "mb_glc":          "buffer_load_dword v1, v0, s[0:3], 0 idxen glc",
 "mb_slc":          "buffer_load_dword v1, v0, s[0:3], 0 idxen slc",
 "mb_tfe":          "buffer_load_dword v[1:2], v0, s[0:3], 0 idxen tfe",
 "mb_addr64":       "buffer_load_dword v1, v[2:3], s[0:3], 0 addr64",
 # ---- MIMG modifiers ----
 "mi_plain":        "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf",
 "mi_glc":          "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf glc",
 "mi_slc":          "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf slc",
 "mi_tfe":          "image_sample v[0:4], v[2:3], s[0:7], s[8:11] dmask:0xf tfe",
 "mi_lwe":          "image_sample v[0:3], v[2:3], s[0:7], s[8:11] dmask:0xf lwe",
 "mi_r128":         "image_sample v[0:3], v[2:3], s[0:3], s[8:11] dmask:0xf r128",
 # ---- VOP3 modifier bit placement ----
 "v3_mad":          "v_mad_f32 v0, v1, v2, v3",
 "v3_mad_clamp":    "v_mad_f32 v0, v1, v2, v3 clamp",
 "v3_mad_abs0":     "v_mad_f32 v0, |v1|, v2, v3",
 "v3_mad_neg0":     "v_mad_f32 v0, -v1, v2, v3",
 "v3_mad_mul2":     "v_mad_f32 v0, v1, v2, v3 mul:2",
 "v3_mad_omod_div2":"v_mad_f32 v0, v1, v2, v3 div:2",
 # ---- literal-constant rules ----
 "lit_vop2":        "v_mul_f32 v0, 0x40000000, v1",
 "lit_vop3_src2":   "v_mad_f32 v0, v1, v2, 0x40000000",
 "lit_vop3_src0":   "v_mad_f32 v0, 0x40000000, v1, v2",
 "lit_vop1":        "v_mov_b32 v0, 0x40000000",
 "lit_vop3_two_sgpr":"v_mad_f32 v0, s1, s2, v3",
 "lit_vop2_two_sgpr":"v_mul_f32 v0, s1, s2",
 "inline_4_0":      "v_mov_b32 v0, 4.0",
 "inline_neg1_0":   "v_mov_b32 v0, -1.0",
 "inline_1_div2pi": "v_mov_b32 v0, 0.15915494",
 # ---- tbuffer syntax hunt ----
 "tb_a":            "tbuffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen dfmt:14 nfmt:7",
 "tb_b":            "tbuffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen format:[BUF_DATA_FORMAT_32_32_32_32,BUF_NUM_FORMAT_FLOAT]",
 "tb_c":            "tbuffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen format:78",
 "tb_d":            "tbuffer_load_format_xyzw v[1:4], v0, s[0:3], 0 idxen",
 "tb_e":            "tbuffer_load_format_x v1, v0, s[0:3], 0 idxen format:[BUF_DATA_FORMAT_32,BUF_NUM_FORMAT_FLOAT]",
 # ---- SMEM extras ----
 "sm_buffer_soff_sgpr": "s_buffer_load_dword s8, s[0:3], s4",
 "sm_buffer_off_max8":  "s_buffer_load_dword s8, s[0:3], 0xff",
 "sm_buffer_off_100":   "s_buffer_load_dword s8, s[0:3], 0x100",
 "sm_load_dwordx2":     "s_load_dwordx2 s[8:9], s[0:1], 0x0",
 "sm_nv":               "s_load_dword s8, s[0:1], 0x0 nv",
 # ---- misc scalar ----
 "sop_s_add_u32":   "s_add_u32 s0, s1, s2",
 "sop_s_and_b64":   "s_and_b64 s[0:1], s[2:3], s[4:5]",
 "sop_s_branch":    "s_branch 0",
 "sop_s_cbranch":   "s_cbranch_scc0 0",
 "sop_s_nop":       "s_nop 0",
 "sop_s_barrier":   "s_barrier",
 "sop_s_sendmsg":   "s_sendmsg sendmsg(MSG_GS_DONE, GS_OP_NOP)",
 "sop_s_movrels":   "s_movrels_b32 s0, s1",
 # ---- VGPR/SGPR indexing, exec ----
 "idx_v_movrels":   "v_movrels_b32 v0, v1",
 "idx_set_gpr_idx": "s_set_gpr_idx_on s0, gpr_idx(SRC0)",
 "exec_s_mov_exec": "s_mov_b64 exec, -1",
 # ---- DS / LDS ----
 "ds_read_b32":     "ds_read_b32 v0, v1",
 "ds_write_b32":    "ds_write_b32 v0, v1",
 "ds_read_b32_off": "ds_read_b32 v0, v1 offset:16",
 # ---- integer / conversion used by a real PS ----
 "cvt_pkrtz":       "v_cvt_pkrtz_f16_f32 v0, v1, v2",
 "cvt_f32_u32":     "v_cvt_f32_u32 v0, v1",
 "cvt_pknorm_i16":  "v_cvt_pknorm_i16_f32 v0, v1, v2",
 "cvt_pk_u8_f32":   "v_cvt_pk_u8_f32 v0, v1, v2, v3",
 "v_fract":         "v_fract_f32 v0, v1",
 "v_rsq":           "v_rsq_f32 v0, v1",
 "v_sqrt":          "v_sqrt_f32 v0, v1",
 "v_log":           "v_log_f32 v0, v1",
 "v_exp":           "v_exp_f32 v0, v1",
 "v_max_f32":       "v_max_f32 v0, v1, v2",
 "v_min_f32":       "v_min_f32 v0, v1, v2",
 "v_lshlrev":       "v_lshlrev_b32 v0, 2, v1",
 "v_and_b32":       "v_and_b32 v0, v1, v2",
 "v_cvt_u32_f32":   "v_cvt_u32_f32 v0, v1",
 "v_mad_u32_u24":   "v_mad_u32_u24 v0, v1, v2, v3",
 "v_trunc":         "v_trunc_f32 v0, v1",
 "v_floor":         "v_floor_f32 v0, v1",
 "v_readfirstlane": "v_readfirstlane_b32 s0, v1",
}
os.makedirs(D, exist_ok=True)
for k, v in P.items():
    open(os.path.join(D, k + ".s"), "w").write(".text\n    " + v + "\n")
print(len(P), "probes written")
