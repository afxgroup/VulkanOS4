target triple = "amdgcn--"

; Kernel args land in the kernarg segment at BYTE offsets 0,8,12,16.
; Whatever offset LLVM's own code generator puts in the s_load reveals the
; units the SMEM offset field uses on that subtarget.
define amdgpu_kernel void @kargs(ptr addrspace(1) %out, i32 %a, i32 %b, i32 %c) {
  %s = add i32 %a, %b
  %t = add i32 %s, %c
  store i32 %t, ptr addrspace(1) %out
  ret void
}

; Explicit constant-address-space load at BYTE offset 128 (32 dwords).
define amdgpu_kernel void @off128(ptr addrspace(4) %p, ptr addrspace(1) %out) {
  %g = getelementptr i32, ptr addrspace(4) %p, i64 32
  %v = load i32, ptr addrspace(4) %g
  store i32 %v, ptr addrspace(1) %out
  ret void
}

; Explicit constant-address-space load at BYTE offset 4 (1 dword).
define amdgpu_kernel void @off4(ptr addrspace(4) %p, ptr addrspace(1) %out) {
  %g = getelementptr i32, ptr addrspace(4) %p, i64 1
  %v = load i32, ptr addrspace(4) %g
  store i32 %v, ptr addrspace(1) %out
  ret void
}
