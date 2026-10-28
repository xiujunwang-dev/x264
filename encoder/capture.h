/* Read-only fixed-state capture. Capture builds are NEVER used for timing. */
#ifndef MCTF_REPLAY_CAPTURE_H
#define MCTF_REPLAY_CAPTURE_H
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static void replay_write(FILE *f, const void *data, size_t bytes)
{
    if (fwrite(data, 1, bytes, f) != bytes) { perror("MCTF capture write"); abort(); }
}

static void capture_mctf_state(x264_t *h, x264_frame_t *frame,
                               x264_frame_t *references[10],
                               int16_t (*ref_mv[10])[2], int num_refs,
                               const int32_t offsets[10], int range, int qp,
                               double strength, const uint8_t *confidence,
                               const int32_t weights[3][1024])
{
    const char *directory = getenv("MCTF_CAPTURE_DIR");
    if (!directory || !*directory) return;
    if (confidence || BIT_DEPTH != 8 || range > 3) abort();
    char path[4096];
    snprintf(path, sizeof(path), "%s/frame-%06d.bin", directory, frame->i_frame);
    FILE *f = fopen(path, "wbx");
    if (!f) { perror(path); abort(); }
    int cw = references[0]->i_width[0], ch = references[0]->i_lines[0];
    int32_t header[12] = {0x4d435246, 1, frame->i_frame, h->param.i_width,
        h->param.i_height, num_refs, cw, ch, h->mb.i_mb_stride,
        h->mb.i_mb_height, qp, range};
    replay_write(f, header, sizeof(header));
    const int32_t inactive[256]={0};
    for (int i=0; i<3; i++)
        replay_write(f, i<range ? weights[i] : inactive, 256*sizeof(int32_t));
    int32_t small_offsets[10], small_weights[3][1024] = {{0}};
    int small_count=0, small_range=range>1?range-1:1;
    for (int i=0; i<num_refs; i++)
        if (abs(offsets[i])<=small_range) small_offsets[small_count++]=offsets[i];
    if (small_count)
        build_mctf_weight_table(small_weights, strength, small_count, small_range, qp, small_offsets, 0);
    for (int i=0; i<3; i++) replay_write(f, small_weights[i], 256*sizeof(int32_t));
    replay_write(f, offsets, num_refs*sizeof(int32_t));
    for (int y=0; y<h->param.i_height; y++)
        replay_write(f, frame->plane[0]+y*frame->i_stride[0], h->param.i_width);
    for (int y=0; y<h->param.i_height; y++)
        replay_write(f, frame->plane_dnr[0]+y*frame->i_stride[0], h->param.i_width);
    for (int i=0; i<num_refs; i++)
    {
        int32_t frame_id = references[i]->i_frame;
        replay_write(f, &frame_id, sizeof(frame_id));
        replay_write(f, ref_mv[i], h->mb.i_mb_stride*h->mb.i_mb_height*2*sizeof(int16_t));
        if (references[i]->i_width[0]!=cw || references[i]->i_lines[0]!=ch) abort();
        for (int y=-32; y<ch+32; y++)
            replay_write(f, references[i]->orig_plane[0]+y*references[i]->i_stride[0]-32, cw+64);
    }
    if (fclose(f)) { perror("MCTF capture close"); abort(); }
}
#endif
