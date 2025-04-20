#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf libuuid-${UUID_VERSION}.tar.gz
pushd libuuid-${UUID_VERSION}

patch -p1 << "EOF"
diff --git a/config.h.in b/config.h.in
index 8eb0959..616f74a 100644
--- a/config.h.in
+++ b/config.h.in
@@ -31,6 +31,15 @@
 /* Define to 1 if you have the <netinet/in.h> header file. */
 #undef HAVE_NETINET_IN_H
 
+/* Define to 1 if you have the <net/if_dl.h> header file. */
+#undef HAVE_NET_IF_DL_H
+
+/* Define to 1 if you have the <net/if.h> header file. */
+#undef HAVE_NET_IF_H
+
+/* Define if struct sockaddr contains sa_len */
+#undef HAVE_SA_LEN
+
 /* Define to 1 if you have the `socket' function. */
 #undef HAVE_SOCKET

diff --git a/configure b/configure
index f73a9ea..9f6a04c 100755
--- a/configure
+++ b/configure
@@ -2083,6 +2095,63 @@ $as_echo "$ac_res" >&6; }
   eval $as_lineno_stack; ${as_lineno_stack:+:} unset as_lineno
 
 } # ac_fn_c_find_uintX_t
+
+# ac_fn_c_check_member LINENO AGGR MEMBER VAR INCLUDES
+# ----------------------------------------------------
+# Tries to find if the field MEMBER exists in type AGGR, after including
+# INCLUDES, setting cache variable VAR accordingly.
+ac_fn_c_check_member ()
+{
+  as_lineno=${as_lineno-"$1"} as_lineno_stack=as_lineno_stack=$as_lineno_stack
+  { $as_echo "$as_me:${as_lineno-$LINENO}: checking for $2.$3" >&5
+$as_echo_n "checking for $2.$3... " >&6; }
+if eval \${$4+:} false; then :
+  $as_echo_n "(cached) " >&6
+else
+  cat confdefs.h - <<_ACEOF >conftest.$ac_ext
+/* end confdefs.h.  */
+$5
+int
+main ()
+{
+static $2 ac_aggr;
+if (ac_aggr.$3)
+return 0;
+  ;
+  return 0;
+}
+_ACEOF
+if ac_fn_c_try_compile "$LINENO"; then :
+  eval "$4=yes"
+else
+  cat confdefs.h - <<_ACEOF >conftest.$ac_ext
+/* end confdefs.h.  */
+$5
+int
+main ()
+{
+static $2 ac_aggr;
+if (sizeof ac_aggr.$3)
+return 0;
+  ;
+  return 0;
+}
+_ACEOF
+if ac_fn_c_try_compile "$LINENO"; then :
+  eval "$4=yes"
+else
+  eval "$4=no"
+fi
+rm -f core conftest.err conftest.$ac_objext conftest.$ac_ext
+fi
+rm -f core conftest.err conftest.$ac_objext conftest.$ac_ext
+fi
+eval ac_res=\$$4q
+	       { $as_echo "$as_me:${as_lineno-$LINENO}: result: $ac_res" >&5
+$as_echo "$ac_res" >&6; }
+  eval $as_lineno_stack; ${as_lineno_stack:+:} unset as_lineno
+
+} # ac_fn_c_check_member
 cat >config.log <<_ACEOF
 This file contains any messages produced by compilers while
 running configure, to aid debugging if configure makes a mistake.
@@ -12306,7 +12375,7 @@ fi
 
 
 # Checks for header files.
-for ac_header in fcntl.h inttypes.h limits.h netinet/in.h stdlib.h string.h sys/file.h sys/ioctl.h sys/socket.h sys/time.h unistd.h
+for ac_header in fcntl.h inttypes.h limits.h net/if.h netinet/in.h net/if_dl.h stdlib.h string.h sys/file.h sys/ioctl.h sys/socket.h sys/time.h unistd.h
 do :
   as_ac_Header=`$as_echo "ac_cv_header_$ac_header" | $as_tr_sh`
 ac_fn_c_check_header_mongrel "$LINENO" "$ac_header" "$as_ac_Header" "$ac_includes_default"
@@ -12445,6 +12514,17 @@ fi
 done
 
 
+
+ac_fn_c_check_member "$LINENO" "struct sockaddr" "sa_len" "ac_cv_member_struct_sockaddr_sa_len" "#include <sys/types.h>
+	 #include <sys/socket.h>
+"
+if test "x$ac_cv_member_struct_sockaddr_sa_len" = xyes; then :
+
+$as_echo "#define HAVE_SA_LEN 1" >>confdefs.h
+
+fi
+
+
 PACKAGE_VERSION_MAJOR=$(echo $PACKAGE_VERSION | awk -F. '{print $1}')
 PACKAGE_VERSION_MINOR=$(echo $PACKAGE_VERSION | awk -F. '{print $2}')
 PACKAGE_VERSION_RELEASE=$(echo $PACKAGE_VERSION | awk -F. '{print $3}')

diff --git a/gen_uuid.c b/gen_uuid.c
index c7b71f2..b52d0fc 100644
--- a/gen_uuid.c
+++ b/gen_uuid.c
@@ -38,6 +38,12 @@
  */
 #define _SVID_SOURCE
 
+#if defined(__linux__)
+  #ifndef _GNU_SOURCE
+    #define _GNU_SOURCE
+  #endif
+#endif
+
 #ifdef _WIN32
 #define _WIN32_WINNT 0x0500
 #include <windows.h>
@@ -175,84 +203,84 @@ static int getuid (void)
  * commenting out get_node_id just to get gen_uuid to compile under windows
  * is not the right way to go!
  */
-static int get_node_id(unsigned char *node_id)
-{
-#ifdef HAVE_NET_IF_H
-	int		sd;
-	struct ifreq	ifr, *ifrp;
-	struct ifconf	ifc;
-	char buf[1024];
-	int		n, i;
-	unsigned char	*a;
-#ifdef HAVE_NET_IF_DL_H
-	struct sockaddr_dl *sdlp;
-#endif
-
-/*
- * BSD 4.4 defines the size of an ifreq to be
- * max(sizeof(ifreq), sizeof(ifreq.ifr_name)+ifreq.ifr_addr.sa_len
- * However, under earlier systems, sa_len isn't present, so the size is
- * just sizeof(struct ifreq)
- */
-#ifdef HAVE_SA_LEN
-#define ifreq_size(i) max(sizeof(struct ifreq),\
-     sizeof((i).ifr_name)+(i).ifr_addr.sa_len)
-#else
-#define ifreq_size(i) sizeof(struct ifreq)
-#endif /* HAVE_SA_LEN */
-
-	sd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
-	if (sd < 0) {
-		return -1;
-	}
-	memset(buf, 0, sizeof(buf));
-	ifc.ifc_len = sizeof(buf);
-	ifc.ifc_buf = buf;
-	if (ioctl (sd, SIOCGIFCONF, (char *)&ifc) < 0) {
-		close(sd);
-		return -1;
-	}
-	n = ifc.ifc_len;
-	for (i = 0; i < n; i+= ifreq_size(*ifrp) ) {
-		ifrp = (struct ifreq *)((char *) ifc.ifc_buf+i);
-		strncpy(ifr.ifr_name, ifrp->ifr_name, IFNAMSIZ);
-#ifdef SIOCGIFHWADDR
-		if (ioctl(sd, SIOCGIFHWADDR, &ifr) < 0)
-			continue;
-		a = (unsigned char *) &ifr.ifr_hwaddr.sa_data;
-#else
-#ifdef SIOCGENADDR
-		if (ioctl(sd, SIOCGENADDR, &ifr) < 0)
-			continue;
-		a = (unsigned char *) ifr.ifr_enaddr;
-#else
-#ifdef HAVE_NET_IF_DL_H
-		sdlp = (struct sockaddr_dl *) &ifrp->ifr_addr;
-		if ((sdlp->sdl_family != AF_LINK) || (sdlp->sdl_alen != 6))
-			continue;
-		a = (unsigned char *) &sdlp->sdl_data[sdlp->sdl_nlen];
-#else
-		/*
-		 * XXX we don't have a way of getting the hardware
-		 * address
-		 */
-		close(sd);
-		return 0;
-#endif /* HAVE_NET_IF_DL_H */
-#endif /* SIOCGENADDR */
-#endif /* SIOCGIFHWADDR */
-		if (!a[0] && !a[1] && !a[2] && !a[3] && !a[4] && !a[5])
-			continue;
-		if (node_id) {
-			memcpy(node_id, a, 6);
-			close(sd);
-			return 1;
-		}
-	}
-	close(sd);
-#endif
-	return 0;
-}
+ static int get_node_id(unsigned char *node_id)
+ {
+ #ifdef HAVE_NET_IF_H
+	 int		sd;
+	 struct ifreq	ifr, *ifrp;
+	 struct ifconf	ifc;
+	 char buf[1024];
+	 int		n, i;
+	 unsigned char	*a = NULL;
+ #ifdef HAVE_NET_IF_DL_H
+	 struct sockaddr_dl *sdlp;
+ #endif
+ 
+ /*
+  * BSD 4.4 defines the size of an ifreq to be
+  * max(sizeof(ifreq), sizeof(ifreq.ifr_name)+ifreq.ifr_addr.sa_len
+  * However, under earlier systems, sa_len isn't present, so the size is
+  * just sizeof(struct ifreq)
+  */
+ #ifdef HAVE_SA_LEN
+ #define ifreq_size(i) max(sizeof(struct ifreq),\
+	  sizeof((i).ifr_name)+(i).ifr_addr.sa_len)
+ #else
+ #define ifreq_size(i) sizeof(struct ifreq)
+ #endif /* HAVE_SA_LEN */
+ 
+	 sd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
+	 if (sd < 0) {
+		 return -1;
+	 }
+	 memset(buf, 0, sizeof(buf));
+	 ifc.ifc_len = sizeof(buf);
+	 ifc.ifc_buf = buf;
+	 if (ioctl (sd, SIOCGIFCONF, (char *)&ifc) < 0) {
+		 close(sd);
+		 return -1;
+	 }
+	 n = ifc.ifc_len;
+	 for (i = 0; i < n; i+= ifreq_size(*ifrp) ) {
+		 ifrp = (struct ifreq *)((char *) ifc.ifc_buf+i);
+		 strncpy(ifr.ifr_name, ifrp->ifr_name, IFNAMSIZ);
+ #ifdef SIOCGIFHWADDR
+		 if (ioctl(sd, SIOCGIFHWADDR, &ifr) < 0)
+			 continue;
+		 a = (unsigned char *) &ifr.ifr_hwaddr.sa_data;
+ #else
+ #ifdef SIOCGENADDR
+		 if (ioctl(sd, SIOCGENADDR, &ifr) < 0)
+			 continue;
+		 a = (unsigned char *) ifr.ifr_enaddr;
+ #else
+ #ifdef HAVE_NET_IF_DL_H
+		 sdlp = (struct sockaddr_dl *) &ifrp->ifr_addr;
+		 if ((sdlp->sdl_family != AF_LINK) || (sdlp->sdl_alen != 6))
+			 continue;
+		 a = (unsigned char *) &sdlp->sdl_data[sdlp->sdl_nlen];
+ #else
+		 /*
+		  * XXX we don't have a way of getting the hardware
+		  * address
+		  */
+		 close(sd);
+		 return 0;
+ #endif /* HAVE_NET_IF_DL_H */
+ #endif /* SIOCGENADDR */
+ #endif /* SIOCGIFHWADDR */
+		 if (a == NULL || (!a[0] && !a[1] && !a[2] && !a[3] && !a[4] && !a[5]))
+			 continue;
+		 if (node_id) {
+			 memcpy(node_id, a, 6);
+			 close(sd);
+			 return 1;
+		 }
+	 }
+	 close(sd);
+ #endif
+	 return 0;
+ }
 
 /* Assume that the gettimeofday() has microsecond granularity */
 #define MAX_ADJUSTMENT 10
EOF

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"

# Error by default in Clang 16.
CFLAGS="${CFLAGS} -Wno-error=implicit-function-declaration"

CFLAGS="${CFLAGS}" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
