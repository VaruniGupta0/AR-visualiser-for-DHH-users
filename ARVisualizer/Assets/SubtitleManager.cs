using UnityEngine;
using TMPro;
using System.Collections;

public class SubtitleManager : MonoBehaviour {
    public TextMeshProUGUI subtitleText;
    public GameObject subtitlePanel; 
    public Transform arCamera; // Drag your AR Camera here in the inspector
    
    [Header("Spatial Settings")]
    public float spawnDistance = 1.5f; // How far away the text hovers (in meters)
    public float heightOffset = -0.2f; // Lowers it slightly so it doesn't block the user's eyes

    public Color priorityColor = Color.yellow;
    public Color normalColor = Color.white;

    private float displayDuration = 4f;
    private Coroutine hideCoroutine;

    public void ShowSubtitle(string text, bool isPriority, string direction) {
        subtitleText.text = text;
        subtitleText.color = isPriority ? priorityColor : normalColor;

        // Calculate where it should appear in 3D space
        PositionInWorld(direction);

        subtitlePanel.SetActive(true);

        if (hideCoroutine != null) StopCoroutine(hideCoroutine);
        hideCoroutine = StartCoroutine(HideAfterDelay());
    }

    void PositionInWorld(string direction) {
        if (arCamera == null) arCamera = Camera.main.transform;

        Vector3 spawnDirection = arCamera.forward;

        // Interpret the backend's directional string
        if (direction == "left") spawnDirection = -arCamera.right;
        else if (direction == "right") spawnDirection = arCamera.right;
        else if (direction == "back") spawnDirection = -arCamera.forward;

        // Flatten the Y axis so the subtitle stays level with the floor, 
        // rather than spawning up in the sky if the user is looking up.
        spawnDirection.y = 0;
        spawnDirection.Normalize();

        Vector3 targetPosition = arCamera.position + (spawnDirection * spawnDistance);
        targetPosition.y += heightOffset; // Apply the vertical offset

        // Move the panel to the target position
        subtitlePanel.transform.position = targetPosition;

        // Make the UI face the camera perfectly
        subtitlePanel.transform.LookAt(subtitlePanel.transform.position + arCamera.forward);
    }

    IEnumerator HideAfterDelay() {
        yield return new WaitForSeconds(displayDuration);
        subtitlePanel.SetActive(false);
    }
}