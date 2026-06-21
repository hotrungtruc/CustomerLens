import { EC2Client, DescribeInstancesCommand } from "@aws-sdk/client-ec2";

const ec2 = new EC2Client({
  region: process.env.AWS_REGION_NAME || "ap-southeast-2",
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID_CONF,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY_CONF,
  },
});

export async function GET() {
  try {
    const command = new DescribeInstancesCommand({
      InstanceIds: [process.env.EC2_INSTANCE_ID],
    });
    const response = await ec2.send(command);
    const instance = response.Reservations[0].Instances[0];
    const state = instance.State.Name; // pending | running | stopping | stopped
    
    return Response.json({
      success: true,
      state: state,
      isOnline: state === "running",
    });
  } catch (error) {
    return Response.json({ success: false, error: error.message }, { status: 500 });
  }
}
