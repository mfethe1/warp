/* exp34 shim: expose the pinned vq.c encoder to ctypes, plus a decoder that
 * is the algebraic inverse of residual VQ (sum of the chosen stage vectors).
 * vq.c and threads.h are BYTE-IDENTICAL to the pinned SHA -- not rewritten. */
#include <stdint.h>
#include <stddef.h>

void waste_vq_encode(const float *X, int n, const float *books, int stages,
                     int entries, int dim, uint8_t *out, int nthreads);
int  waste_vq_lloyd(const float *X, int n, float *C, int entries, int dim,
                    int nthreads);

/* reconstruct X_hat[n][dim] from codes[n][stages] */
void exp34_decode(const uint8_t *codes, const float *books, int n, int stages,
                  int entries, int dim, float *out)
{
    for (int i = 0; i < n; i++) {
        float *o = out + (size_t)i * dim;
        for (int d = 0; d < dim; d++) o[d] = 0.f;
        for (int s = 0; s < stages; s++) {
            const int c = codes[(size_t)i * stages + s];
            const float *e = books + ((size_t)s * entries + c) * dim;
            for (int d = 0; d < dim; d++) o[d] += e[d];
        }
    }
}
