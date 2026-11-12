/* Presentation geometry only; see docs/reviews/road-wobble.md. */
#include "tg2_road_fit.h"
#include <math.h>
#include <stdlib.h>

#define FIT_BEND 64.0

/* Bounded Whittaker fit. The Hessian is pentadiagonal; solve each free set
 * with banded Cholesky in O(n). Fix violated bounds, then release a bound
 * whose multiplier has the wrong sign. Unlike clipping a filtered curve,
 * active constraints participate in the solve, so their neighbours stay smooth.
 * Missing observations (a different stripe template) carry no data weight. */
void tg2_road_fit(const double *raw, const unsigned char *seen, int n,
                  double *out) {
    double diag[TG2_ROAD_FIT_ROWS], off[TG2_ROAD_FIT_ROWS] = {0};
    double off2[TG2_ROAD_FIT_ROWS] = {0}, rhs[TG2_ROAD_FIT_ROWS];
    signed char fixed[TG2_ROAD_FIT_ROWS] = {0};
    for (int i = 0; i < n; ++i) {
        diag[i] = seen[i] ? 1.0 : 0.0;
        out[i] = raw[i];
    }
    if (n < 3) return;
    for (int i = 0; i + 2 < n; ++i) {
        diag[i] += FIT_BEND; diag[i+1] += 4*FIT_BEND; diag[i+2] += FIT_BEND;
        off[i+1] -= 2*FIT_BEND; off[i+2] -= 2*FIT_BEND;
        off2[i+2] += FIT_BEND;
    }
    /* Each iteration either adds an active constraint or releases one.
     * The guard is defensive; the feasible authored data is the fallback. */
    for (int iteration = 0; iteration < 4*n; ++iteration) {
        double d[TG2_ROAD_FIT_ROWS], l[TG2_ROAD_FIT_ROWS], l2[TG2_ROAD_FIT_ROWS];
        for (int i = 0; i < n; ++i) {
            rhs[i] = seen[i] ? raw[i] : 0;
            d[i] = fixed[i] ? 1.0 : diag[i];
            l[i] = i && !fixed[i] && !fixed[i-1] ? off[i] : 0;
            l2[i] = i > 1 && !fixed[i] && !fixed[i-2] ? off2[i] : 0;
            if (fixed[i]) { rhs[i] = out[i]; continue; }
            for (int j = i-2; j <= i+2; ++j) {
                if (j < 0 || j >= n || !fixed[j]) continue;
                int delta = abs(j-i);
                rhs[i] -= (delta == 1 ? off[i > j ? i : j] :
                           delta == 2 ? off2[i > j ? i : j] : 0) * out[j];
            }
        }
        for (int i = 0; i < n; ++i) {
            if (i > 1) l2[i] /= d[i-2];
            if (i) l[i] = (l[i] - (i > 1 ? l2[i]*l[i-1] : 0)) / d[i-1];
            d[i] = sqrt(d[i] - l[i]*l[i] - l2[i]*l2[i]);
            rhs[i] = (rhs[i] - (i ? l[i]*rhs[i-1] : 0) -
                       (i > 1 ? l2[i]*rhs[i-2] : 0)) / d[i];
        }
        for (int i = n-1; i >= 0; --i)
            out[i] = (rhs[i] - (i+1 < n ? l[i+1]*out[i+1] : 0) -
                      (i+2 < n ? l2[i+2]*out[i+2] : 0)) / d[i];
        int added = 0;
        for (int i = 0; i < n; ++i) {
            if (fixed[i] || !seen[i]) continue;
            if (out[i] < raw[i]-TG2_ROAD_FIT_LIMIT || out[i] > raw[i]+TG2_ROAD_FIT_LIMIT) {
                fixed[i] = out[i] < raw[i] ? -1 : 1;
                out[i] = raw[i] + fixed[i]*TG2_ROAD_FIT_LIMIT;
                added = 1;
            }
        }
        if (added) continue;
        double worst = 1e-7;
        int release = -1;
        for (int i = 0; i < n; ++i) {
            if (!fixed[i]) continue;
            double gradient = diag[i]*out[i] - raw[i];
            if (i) gradient += off[i]*out[i-1];
            if (i+1 < n) gradient += off[i+1]*out[i+1];
            if (i > 1) gradient += off2[i]*out[i-2];
            if (i+2 < n) gradient += off2[i+2]*out[i+2];
            double violation = fixed[i]*gradient;
            if (violation > worst) { worst = violation; release = i; }
        }
        if (release < 0) return;
        fixed[release] = 0;
    }
    for (int i = 0; i < n; ++i) out[i] = raw[i];
}

