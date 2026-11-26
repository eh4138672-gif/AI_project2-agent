# Verify HTTPS certificates with the Windows certificate store (like Chrome does).
# Needed behind filters such as NetFree, whose certificate Python 3.13 rejects by default.
import truststore

truststore.inject_into_ssl()
