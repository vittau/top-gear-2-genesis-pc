/* TG2 video: debug (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

#ifdef GEN_ENABLE_TRACE
void tg2_video_command(int id, const char *json) {
    char out[22000];
    int n = snprintf(out, sizeof out,
                     "{\"id\":%d,\"ok\":true,\"enabled\":%d,\"wide_lines\":%u,\"native_lines\":%u,"
                     "\"published\":%u,\"displayed\":%u,\"pieces\":%u,\"overflow\":%u,"
                     "\"sat_matches\":%u,\"margin_pieces\":%u,\"sprite_margin_pixels\":%u,"
                     "\"hud_edges\":%d,\"hud_plane_pixels\":%u,\"hud_marker_pixels\":%u,"
                     "\"hud_sprite_pixels\":%u,"
                     "\"hide_overscan\":%d,\"crop\":%d,\"crop_frames\":%u,"
                     "\"crop_withheld\":%u",
                     id, tg2v_enabled(), tg2v_wide_lines, tg2v_native_lines, tg2v_serial, tg2v_shown ? tg2v_shown->serial : 0,
                     tg2v_shown ? tg2v_shown->count : 0, tg2v_overflow, tg2v_matched_pieces, tg2v_margin_pieces,
                     tg2v_frame_margin_pixels, tg2v_tg2_video_get_hud_mode(), tg2v_hud_plane_pixels, tg2v_hud_marker_pixels,
                     tg2v_hud_sprite_pixels,
                     tg2v_tg2_video_get_hide_overscan(), tg2v_presented_cropped, tg2v_crop_frames,
                     tg2v_crop_withheld);
    n += snprintf(out + n, sizeof out - n,
                  ",\"race60\":%d,\"presentation_delay_frames\":%d,\"presentation_frame\":%llu,"
                  "\"from_frame\":%llu,\"to_frame\":%llu,\"phase_num\":%u,\"phase_den\":%u",
                  tg2v_race60, PRESENT_DELAY, (unsigned long long)tg2v_present_frame,
                  (unsigned long long)(tg2v_from_picture ? tg2v_from_picture->frame : 0),
                  (unsigned long long)(tg2v_to_picture ? tg2v_to_picture->frame : 0), tg2v_phase_num, tg2v_phase_den);
    n += snprintf(out + n, sizeof out - n,
                  ",\"highres_scale\":%d,\"highres_present_scale\":%d,"
                  "\"highres_capture_frames\":%u,"
                  "\"highres_capture_us\":%.3f,\"highres_capture_rows\":%u,"
                  "\"highres_build_frames\":%u,\"highres_build_us\":%.3f",
                  tg2_highres_scale(), tg2_highres_scale(),
                  tg2_highres_capture_frames(),
                  tg2_highres_capture_us(), tg2_highres_capture_rows_done(),
                  tg2_highres_build_frames(), tg2_highres_build_us());
    if (json && strstr(json, "\"rows\"")) {
        n += snprintf(out + n, sizeof out - n, ",\"rows\":[");
        for (int i = 0; i < 224; ++i)
            n += snprintf(out + n, sizeof out - n, "%s[%d,%d,%d,%d,%u,%u]", i ? "," : "",
                          tg2v_rows[i].ha, tg2v_rows[i].hb, tg2v_rows[i].va, tg2v_rows[i].vb, tg2v_rows[i].a, tg2v_rows[i].b);
        n += snprintf(out + n, sizeof out - n, "]");
    }
    if (json && strstr(json, "\"top\"")) {
        n += snprintf(out + n, sizeof out - n, ",\"top\":[");
        for (int row = 0; row < 8; ++row) {
            n += snprintf(out + n, sizeof out - n, "%s{\"reg\":[", row ? "," : "");
            for (int i = 0; i < 24; ++i)
                n += snprintf(out + n, sizeof out - n, "%s%u", i ? "," : "", tg2v_top_rows[row].reg[i]);
            n += snprintf(out + n, sizeof out - n, "],\"vsram\":[%u,%u],\"cram\":[",
                          tg2v_top_rows[row].vsram[0], tg2v_top_rows[row].vsram[1]);
            for (int i = 0; i < 64; ++i)
                n += snprintf(out + n, sizeof out - n, "%s%u", i ? "," : "", tg2v_top_rows[row].cram[i]);
            n += snprintf(out + n, sizeof out - n, "]}");
        }
        n += snprintf(out + n, sizeof out - n, "]");
    }
    snprintf(out + n, sizeof out - n, "}");
    cmd_send_response(out);
}
/* S1 evidence: the captured compact row state next to the live per-row words
 * the renderer used for the same picture (rows[] is written in the same branch
 * as the capture). Rows whose serial is not the latest picture were skipped by
 * the renderer (for example the blanked overscan band) and must not be
 * compared. */
void tg2_video_highres_command(int id, const char *json) {
    enum { CAPACITY = 262144 };
    char *out = malloc(CAPACITY);
    if (!out) {
        cmd_send_response("{\"ok\":false,\"error\":\"out of memory\"}");
        return;
    }
    /* {"dump":"path"}: N x pictures also write their 1x canvas ("" stops). */
    const char *dump = json ? strstr(json, "\"dump\"") : NULL;
    if (dump && (dump = strchr(dump + 6, '"')) != NULL) {
        char path[1024];
        size_t length = strcspn(dump + 1, "\"");
        if (length < sizeof path) {
            memcpy(path, dump + 1, length);
            path[length] = 0;
            tg2_highres_request_native_dump(path);
        }
    }
    const Tg2RowState *captured = tg2_highres_rows();
    const unsigned *row_serial = tg2_highres_row_serial();
    unsigned tg2v_serial = tg2_highres_serial();
    int n = snprintf(out, CAPACITY,
                     "{\"id\":%d,\"ok\":true,\"scale\":%d,\"present_scale\":%d,"
                     "\"capture_frames\":%u,\"serial\":%u,"
                     "\"capture_us\":%.3f,\"capture_rows\":%u,"
                     "\"build_frames\":%u,\"build_us\":%.3f",
                     id, tg2_highres_scale(), tg2_highres_scale(),
                     tg2_highres_capture_frames(),
                     tg2v_serial, tg2_highres_capture_us(),
                     tg2_highres_capture_rows_done(),
                     tg2_highres_build_frames(), tg2_highres_build_us());
    if (json && strstr(json, "\"rows\"") && n > 0 && n < CAPACITY) {
        n += snprintf(out + n, CAPACITY - n, ",\"rows\":[");
        for (int line = 0; line < TG2_HIGHRES_ROWS && n > 0 && n < CAPACITY; ++line) {
            const Tg2RowState *r = &captured[line];
            n += snprintf(out + n, CAPACITY - n,
                          "%s{\"gen\":%u,\"ha\":%u,\"hb\":%u,\"va\":%u,\"vb\":%u,"
                          "\"hscroll\":[%u,%u],\"bank\":[%u,%u],\"k\":%d,\"flags\":%u}",
                          line ? "," : "", row_serial[line], r->hscroll[0], r->hscroll[1],
                          r->vsram[0], r->vsram[1], r->hscroll[0], r->hscroll[1],
                          r->bank[0], r->bank[1], r->width_k, r->flags);
        }
        n += snprintf(out + n, CAPACITY - n, "],\"live\":[");
        for (int line = 0; line < 224 && n > 0 && n < CAPACITY; ++line)
            n += snprintf(out + n, CAPACITY - n,
                          "%s{\"ha\":%d,\"hb\":%d,\"va\":%d,\"vb\":%d}",
                          line ? "," : "", tg2v_rows[line].ha, tg2v_rows[line].hb,
                          tg2v_rows[line].va, tg2v_rows[line].vb);
        n += snprintf(out + n, CAPACITY - n, "]");
    }
    if (n > 0 && n < CAPACITY)
        n += snprintf(out + n, CAPACITY - n, ",\"filtered_frames\":%u,\"filter_incomplete\":%u,\"native_filter\":%d",
                      tg2_highres_filtered_frames(), tg2_highres_filter_incomplete(),
                      tg2_highres_linear_filter());
    if (n>0 && n<CAPACITY) n+=snprintf(out+n,CAPACITY-n,",\"actor_rows\":%llu,\"actor_row_mismatches\":%llu,\"actor_dropped\":%u,\"native_objects\":%u,\"actors\":",tg2v_actor_rows,tg2v_actor_row_mismatches,tg2_actors_dropped(),tg2_actors_native_objects());
    if (n>0 && n<CAPACITY) n+=tg2_actors_json(out+n,CAPACITY-n);
    if (n>0 && n<CAPACITY) n+=snprintf(out+n,CAPACITY-n,",\"all_actors\":");
    if (n>0 && n<CAPACITY) n+=tg2_actors_stats_json(out+n,CAPACITY-n);
    if (n > 0 && n < CAPACITY) snprintf(out + n, CAPACITY - n, "}");
    cmd_send_response(out);
    free(out);
}
#endif
