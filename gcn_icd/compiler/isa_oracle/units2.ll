target triple = "amdgcn--"
; byte offset 4096 (= dword 1024) : exceeds the 8-bit gfx6/7 immediate field
define amdgpu_kernel void @off4096(ptr addrspace(4) %p, ptr addrspace(1) %out) {
  %g = getelementptr i32, ptr addrspace(4) %p, i64 1024
  %v = load i32, ptr addrspace(4) %g
  store i32 %v, ptr addrspace(1) %out
  ret void
}
; byte offset 1020 (= dword 255) : the largest that still fits gfx6/7's 8-bit field
define amdgpu_kernel void @off1020(ptr addrspace(4) %p, ptr addrspace(1) %out) {
  %g = getelementptr i32, ptr addrspace(4) %p, i64 255
  %v = load i32, ptr addrspace(4) %g
  store i32 %v, ptr addrspace(1) %out
  ret void
}
; byte offset 1024 (= dword 256) : one past gfx6/7's 8-bit field
define amdgpu_kernel void @off1024(ptr addrspace(4) %p, ptr addrspace(1) %out) {
  %g = getelementptr i32, ptr addrspace(4) %p, i64 256
  %v = load i32, ptr addrspace(4) %g
  store i32 %v, ptr addrspace(1) %out
  ret void
}
