/* Configuration extracted from CMake'd project files.

This is used by CPython, and is not part of the regular xz release.
*/

#define HAVE_CHECK_CRC32 1
#define HAVE_CHECK_CRC64 1
#define HAVE_CHECK_SHA256 1

#define HAVE_DECODERS 1
#define HAVE_DECODER_ARM 1
#define HAVE_DECODER_ARM64 1
#define HAVE_DECODER_ARMTHUMB 1
#define HAVE_DECODER_DELTA 1
#define HAVE_DECODER_IA64 1
#define HAVE_DECODER_POWERPC 1
#define HAVE_DECODER_LZMA1 1
#define HAVE_DECODER_LZMA2 1
#define HAVE_DECODER_SPARC 1
#define HAVE_DECODER_X86 1

#define HAVE_ENCODERS 1
#define HAVE_ENCODER_ARM 1
#define HAVE_ENCODER_ARM64 1
#define HAVE_ENCODER_ARMTHUMB 1
#define HAVE_ENCODER_DELTA 1
#define HAVE_ENCODER_IA64 1
#define HAVE_ENCODER_POWERPC 1
#define HAVE_ENCODER_LZMA1 1
#define HAVE_ENCODER_LZMA2 1
#define HAVE_ENCODER_SPARC 1
#define HAVE_ENCODER_X86 1

#if defined(_M_ARM64)

#undef HAVE_IMMINTRIN_H
#undef HAVE_USABLE_CLMUL

#else

#define HAVE_IMMINTRIN_H 1
#define HAVE_USABLE_CLMUL 1
#define HAVE__MM_MOVEMASK_EPI8 1
#define TUKLIB_FAST_UNALIGNED_ACCESS 1

#endif

#define HAVE___BUILTIN_ASSUME_ALIGNED 1
#define HAVE__BOOL 1

#define HAVE_INTTYPES_H 1
#define HAVE_MF_BT2 1
#define HAVE_MF_BT3 1
#define HAVE_MF_BT4 1
#define HAVE_MF_HC3 1
#define HAVE_MF_HC4 1
#define HAVE_STDBOOL_H 1
#define HAVE_STDINT_H 1
#define HAVE_VISIBILITY 0

#define MYTHREAD_VISTA 1

#define PACKAGE_BUGREPORT "xz@tukaani.org"
#define PACKAGE_NAME "XZ Utils"
#define PACKAGE_URL "https://tukaani.org/xz/"

#define TUKLIB_SYMBOL_PREFIX lzma_
